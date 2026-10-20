package com.alassali.fastinventory

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import java.nio.charset.StandardCharsets
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

object ReportExportEngine {

    data class ExportResult(
        val csvFile: File,
        val xlsxFile: File,
        val summaryText: String
    )

    /**
     * Generates both a multi-sheet XLSX workbook and a companion UTF-8 BOM CSV for the given session.
     * Incorporates target Showroom/Warehouse stock comparison, entry method, and physical shelf sequence.
     */
    fun exportSessionReport(
        context: Context,
        sessionName: String,
        zoneName: String,
        items: List<ScanRecord>,
        db: InventoryDatabase,
        warehouseName: String = ""
    ): ExportResult {
        val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val cleanName = sessionName.replace("[^a-zA-Z0-9_\\-\\u0600-\\u06FF]".toRegex(), "_")

        val cacheDir = context.cacheDir
        val csvFile = File(cacheDir, "FastInventory_${cleanName}_$dateStamp.csv")
        val xlsxFile = File(cacheDir, "FastInventory_${cleanName}_$dateStamp.xlsx")

        val settings = SettingsManager(context)
        val sId = if (items.isNotEmpty()) items.first().sessionId else 0L
        val dbSession = if (sId > 0) db.getSessionById(sId) else null

        val whId = if (dbSession != null && dbSession.warehouseId > 0) dbSession.warehouseId else settings.getSelectedWarehouseId()
        val whCode = if (dbSession != null && dbSession.warehouseCode.isNotBlank()) dbSession.warehouseCode else settings.getSelectedWarehouseCode()
        val whName = if (warehouseName.isNotBlank() && warehouseName != "المخزون العام للشركة") {
            warehouseName
        } else if (dbSession != null && dbSession.warehouseName.isNotBlank()) {
            dbSession.warehouseName
        } else {
            settings.getSelectedWarehouseName()
        }
        val lotStockId = settings.getSelectedWarehouseLotStockId()
        val devName = settings.getDeviceName()
        val sessionDate = dbSession?.createdAt ?: SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(Date())
        val exportTime = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())

        val metadata = InventoryReportMetadata(
            sessionName = sessionName,
            sessionId = sId,
            warehouseId = whId,
            warehouseCode = whCode,
            warehouseName = whName,
            lotStockId = lotStockId,
            zoneName = zoneName,
            deviceName = devName,
            createdAt = sessionDate,
            exportTimestamp = exportTime,
            isConsolidated = false
        )

        // 1. Build Consolidated Items with System Quantities & Cost
        val consolidatedList = mutableListOf<ConsolidatedItem>()
        val unknownList = mutableListOf<ScanRecord>()

        var totalCounted = 0.0
        var totalSystem = 0.0
        var totalVarianceVal = 0.0
        var manualCount = 0

        for (rec in items) {
            val prod = db.getProductByBarcodeOrCode(rec.barcode)
            if (prod == null) {
                unknownList.add(rec)
            }
            if (rec.scanMethod == "MANUAL") {
                manualCount++
            }
            val sysQty = prod?.systemQty ?: 0.0
            val cost = prod?.standardPrice ?: 0.0
            val listPrice = prod?.listPrice ?: 0.0

            val item = ConsolidatedItem(
                barcode = rec.barcode,
                defaultCode = prod?.defaultCode ?: rec.defaultCode,
                nameAr = prod?.nameAr ?: rec.nameAr,
                nameEn = prod?.nameEn ?: rec.nameEn,
                countedQty = rec.qty,
                systemQty = sysQty,
                costPrice = cost,
                listPrice = listPrice,
                scanMethod = rec.scanMethod
            )
            item.zoneCounts[rec.zoneName] = rec.qty
            consolidatedList.add(item)

            totalCounted += rec.qty
            totalSystem += sysQty
            totalVarianceVal += item.varianceValue
        }

        // Fetch detailed raw scans for full audit trail and physical shelf walk
        val rawScans = if (items.isNotEmpty()) {
            db.getAllScansForSession(sId)
        } else emptyList()

        // 2. Write CSV with UTF-8 BOM
        writeCsvReport(csvFile, metadata, consolidatedList, unknownList, rawScans)

        // 3. Write Pure-Kotlin Multi-Sheet XLSX
        writeXlsxWorkbook(xlsxFile, metadata, consolidatedList, unknownList, rawScans)

        val netVariance = totalCounted - totalSystem
        val matchedCount = consolidatedList.count { it.varianceQty == 0.0 }
        val shortageCount = consolidatedList.count { it.varianceQty < 0.0 }
        val surplusCount = consolidatedList.count { it.varianceQty > 0.0 }
        val accuracyPct = if (consolidatedList.isNotEmpty()) (matchedCount.toDouble() / consolidatedList.size.toDouble()) * 100.0 else 100.0

        val summaryText = """
            🏢 تقرير جرد ومطابقة المخزون — شركة العسلي المحدودة
            ════════════════════════════════════════
            • المعرض / المستودع: ${metadata.warehouseName}
            • رقم المعرض في Odoo (ID): ${if (metadata.warehouseId > 0) metadata.warehouseId.toString() else "المخزون العام"}
            • كود المعرض: ${metadata.warehouseCode.ifBlank { "WH" }}
            • اسم جلسة الجرد: ${metadata.sessionName}
            • تاريخ وتوقيت الجرد: ${metadata.createdAt}
            • تاريخ إصدار التقرير: ${metadata.exportTimestamp}
            • الجهاز / المدقق: ${metadata.deviceName}
            • نطاق الجرد (المنطقة/الرف): ${metadata.zoneName}
            ────────────────────────────────────────
            📊 مؤشرات المطابقة والأداء:
            • عدد الأصناف الفريدة: ${consolidatedList.size} صنف
            • إجمالي الحبات الفعلية: ${String.format(Locale.US, "%.0f", totalCounted)} حبة
            • رصيد Odoo بالمعرض: ${String.format(Locale.US, "%.0f", totalSystem)} حبة
            • صافي فرق الكمية: ${if (netVariance > 0) "+${String.format(Locale.US, "%.0f", netVariance)}" else String.format(Locale.US, "%.0f", netVariance)} حبة
            • إجمالي قيمة الفروقات: ${String.format(Locale.US, "%.2f", totalVarianceVal)} ر.س
            • نسبة دقة الجرد: ${String.format(Locale.US, "%.1f", accuracyPct)}%
            • أصناف مطابقة 100%: $matchedCount صنف
            • أصناف بها عجز (نقص): $shortageCount صنف
            • أصناف بها فائض (زيادة): $surplusCount صنف
            • أصناف مدخلة يدوياً: $manualCount صنف
            • أصناف غير معرّفة بالنظام: ${unknownList.size} صنف
        """.trimIndent()

        return ExportResult(csvFile, xlsxFile, summaryText)
    }

    /**
     * Exports a multi-device consolidated report.
     */
    fun exportConsolidatedReport(
        context: Context,
        reportTitle: String,
        consolidatedItems: List<ConsolidatedItem>,
        deviceNames: List<String>,
        db: InventoryDatabase,
        warehouseName: String = "المخزون العام للشركة"
    ): ExportResult {
        val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val cleanName = reportTitle.replace("[^a-zA-Z0-9_\\-\\u0600-\\u06FF]".toRegex(), "_")

        val cacheDir = context.cacheDir
        val csvFile = File(cacheDir, "Consolidated_${cleanName}_$dateStamp.csv")
        val xlsxFile = File(cacheDir, "Consolidated_${cleanName}_$dateStamp.xlsx")

        val settings = SettingsManager(context)
        val whId = settings.getSelectedWarehouseId()
        val whCode = settings.getSelectedWarehouseCode()
        val whName = if (warehouseName.isNotBlank() && warehouseName != "المخزون العام للشركة") warehouseName else settings.getSelectedWarehouseName()
        val lotStockId = settings.getSelectedWarehouseLotStockId()
        val exportTime = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())

        val metadata = InventoryReportMetadata(
            sessionName = reportTitle,
            sessionId = 0L,
            warehouseId = whId,
            warehouseCode = whCode,
            warehouseName = whName,
            lotStockId = lotStockId,
            zoneName = "كافة المناطق والرفوف المدمجة",
            deviceName = deviceNames.joinToString("، "),
            createdAt = exportTime,
            exportTimestamp = exportTime,
            isConsolidated = true,
            deviceList = deviceNames
        )

        var totalCounted = 0.0
        var totalSystem = 0.0
        var totalVarianceVal = 0.0

        for (item in consolidatedItems) {
            totalCounted += item.countedQty
            totalSystem += item.systemQty
            totalVarianceVal += item.varianceValue
        }

        writeCsvReport(csvFile, metadata, consolidatedItems, emptyList(), emptyList())
        writeXlsxWorkbook(xlsxFile, metadata, consolidatedItems, emptyList(), emptyList())

        val netVariance = totalCounted - totalSystem
        val matchedCount = consolidatedItems.count { it.varianceQty == 0.0 }
        val shortageCount = consolidatedItems.count { it.varianceQty < 0.0 }
        val surplusCount = consolidatedItems.count { it.varianceQty > 0.0 }
        val accuracyPct = if (consolidatedItems.isNotEmpty()) (matchedCount.toDouble() / consolidatedItems.size.toDouble()) * 100.0 else 100.0

        val summaryText = """
            🔀 تقرير الجرد المدمج للأجهزة المتعددة — شركة العسلي المحدودة
            ════════════════════════════════════════
            • المعرض / المستودع: ${metadata.warehouseName}
            • رقم المعرض في Odoo (ID): ${if (metadata.warehouseId > 0) metadata.warehouseId.toString() else "المخزون العام"}
            • كود المعرض: ${metadata.warehouseCode.ifBlank { "WH" }}
            • الأجهزة المشاركة: ${deviceNames.joinToString("، ")}
            • تاريخ وتوقيت الدمج: ${metadata.exportTimestamp}
            ────────────────────────────────────────
            📊 مؤشرات المطابقة والأداء:
            • عدد الأصناف الفريدة: ${consolidatedItems.size} صنف
            • إجمالي الحبات المحصورة: ${String.format(Locale.US, "%.0f", totalCounted)} حبة
            • رصيد Odoo بالمعرض: ${String.format(Locale.US, "%.0f", totalSystem)} حبة
            • صافي فرق الكمية: ${if (netVariance > 0) "+${String.format(Locale.US, "%.0f", netVariance)}" else String.format(Locale.US, "%.0f", netVariance)} حبة
            • قيمة الفروقات: ${String.format(Locale.US, "%.2f", totalVarianceVal)} ر.س
            • نسبة دقة الجرد: ${String.format(Locale.US, "%.1f", accuracyPct)}%
            • أصناف مطابقة 100%: $matchedCount صنف
            • أصناف بها عجز (نقص): $shortageCount صنف
            • أصناف بها فائض (زيادة): $surplusCount صنف
        """.trimIndent()

        return ExportResult(csvFile, xlsxFile, summaryText)
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CSV Generator (UTF-8 with BOM for 100% Arabic Excel Compatibility)
    // ─────────────────────────────────────────────────────────────────────────
    private fun writeCsvReport(
        file: File,
        metadata: InventoryReportMetadata,
        items: List<ConsolidatedItem>,
        unknowns: List<ScanRecord>,
        rawScans: List<ScanRecord>
    ) {
        FileOutputStream(file).use { fos ->
            fos.write(byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()))

            OutputStreamWriter(fos, StandardCharsets.UTF_8).use { writer ->
                val totalCounted = items.sumOf { it.countedQty }
                val totalSystem = items.sumOf { it.systemQty }
                val netVariance = totalCounted - totalSystem
                val totalVarianceVal = items.sumOf { it.varianceValue }
                val matchedCount = items.count { it.varianceQty == 0.0 }
                val shortageCount = items.count { it.varianceQty < 0.0 }
                val surplusCount = items.count { it.varianceQty > 0.0 }
                val manualCount = items.count { it.scanMethod == "MANUAL" }
                val accuracyPct = if (items.isNotEmpty()) (matchedCount.toDouble() / items.size.toDouble()) * 100.0 else 100.0

                writer.append("═══════════════════════════════════════════════════════════════════════════════\n")
                writer.append("تقرير جرد ومطابقة المخزون الميداني مع نظام Odoo ERP — شركة العسلي المحدودة\n")
                writer.append("═══════════════════════════════════════════════════════════════════════════════\n")
                writer.append("المعرض / المستودع:,${escapeCsv(metadata.warehouseName)},رقم المعرض في Odoo:,${metadata.warehouseId},كود المعرض:,${metadata.warehouseCode}\n")
                writer.append("جلسة الجرد:,${escapeCsv(metadata.sessionName)},تاريخ بدء الجرد:,${metadata.createdAt},تاريخ استخراج التقرير:,${metadata.exportTimestamp}\n")
                writer.append("جهاز الجرد / المدقق:,${escapeCsv(metadata.deviceName)},نطاق الجرد (المنطقة/الرف):,${escapeCsv(metadata.zoneName)},موقع التخزين:,${if (metadata.lotStockId > 0) "Location ID " + metadata.lotStockId else "الافتراضي"}\n")
                writer.append("إجمالي الأصناف:,${items.size} صنف,إجمالي الحبات الفعلية:,${String.format(Locale.US, "%.0f", totalCounted)},رصيد Odoo بالمعرض:,${String.format(Locale.US, "%.0f", totalSystem)}\n")
                writer.append("صافي فرق الحبات:,${String.format(Locale.US, "%.0f", netVariance)},قيمة الفروقات (ر.س):,${String.format(Locale.US, "%.2f", totalVarianceVal)},نسبة دقة الجرد:,${String.format(Locale.US, "%.1f", accuracyPct)}%\n")
                writer.append("أصناف مطابقة 100%:,${matchedCount} صنف,أصناف عجز:,${shortageCount} صنف,أصناف فائض:,${surplusCount} صنف,أصناف يدوية:,${manualCount} صنف\n")
                writer.append("═══════════════════════════════════════════════════════════════════════════════\n\n")

                writer.append("الباركود,كود الصنف,اسم المنتج بالعربي,اسم المنتج بالإنجليزي,الكمية المحصورة (الفعلي),رصيد المعرض في أودو,فرق الجرد,سعر التكلفة,قيمة الفرق (ر.س),سعر البيع,طريقة الإدخال\n")

                for (item in items) {
                    val escNameAr = escapeCsv(item.nameAr)
                    val escNameEn = escapeCsv(item.nameEn)
                    val methodLabel = if (item.scanMethod == "MANUAL") "إدخال يدوي" else "مسح ليزر/كاميرا"
                    writer.append("${item.barcode},${item.defaultCode},$escNameAr,$escNameEn,${item.countedQty},${item.systemQty},${item.varianceQty},${item.costPrice},${String.format(Locale.US, "%.2f", item.varianceValue)},${item.listPrice},$methodLabel\n")
                }

                if (rawScans.isNotEmpty()) {
                    writer.append("\n\n--- سجل وتفاصيل الجرد الميداني (Audit Trail) ---\n")
                    writer.append("تسلسل الرف,المنطقة / الرف,مستوى الرف,الباركود,كود الصنف,اسم المنتج,الكمية,طريقة الإدخال,نوع المسح,الجهاز,التوقيت\n")
                    for (s in rawScans) {
                        val methodDesc = when (s.scanMethod) {
                            "MANUAL" -> "إدخال يدوي"
                            "OVERRIDE" -> "تعديل كمية"
                            else -> "مسح ليزر/كاميرا"
                        }
                        val pkgDesc = if (s.isPackaging) "كرتون (${s.packagingQty}) - ${s.packagingName}" else "مفرد"
                        writer.append("${s.shelfSeq},${escapeCsv(s.zoneName)},${escapeCsv(s.shelfLevel)},${s.barcode},${s.defaultCode},${escapeCsv(s.nameAr)},${s.qty},$methodDesc,$pkgDesc,${escapeCsv(s.deviceName)},${s.timestamp}\n")
                    }
                }

                if (unknowns.isNotEmpty()) {
                    writer.append("\n\n--- أصناف ممسوحة غير معرّفة في أودو ---\n")
                    writer.append("الباركود,المنطقة,الكمية المحصورة,الجهاز,التوقيت\n")
                    for (u in unknowns) {
                        writer.append("${u.barcode},${escapeCsv(u.zoneName)},${u.qty},${escapeCsv(u.deviceName)},${u.timestamp}\n")
                    }
                }
            }
        }
    }

    private fun escapeCsv(value: String): String {
        return if (value.contains(",") || value.contains("\"") || value.contains("\n")) {
            "\"${value.replace("\"", "\"\"")}\""
        } else {
            value
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Pure-Kotlin Zero-Dependency Multi-Sheet XLSX Builder
    // ─────────────────────────────────────────────────────────────────────────
    private fun writeXlsxWorkbook(
        file: File,
        metadata: InventoryReportMetadata,
        consolidated: List<ConsolidatedItem>,
        unknowns: List<ScanRecord>,
        rawScans: List<ScanRecord>
    ) {
        ZipOutputStream(FileOutputStream(file)).use { zip ->
            // 1. [Content_Types].xml
            addZipEntry(zip, "[Content_Types].xml", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                    <Default Extension="xml" ContentType="application/xml"/>
                    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
                    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
                    <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
                    <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
                    <Override PartName="/xl/worksheets/sheet4.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
                    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
                </Types>
            """.trimIndent())

            // 2. _rels/.rels
            addZipEntry(zip, "_rels/.rels", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
                </Relationships>
            """.trimIndent())

            // 3. xl/_rels/workbook.xml.rels
            addZipEntry(zip, "xl/_rels/workbook.xml.rels", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
                    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
                    <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
                    <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet4.xml"/>
                    <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
                </Relationships>
            """.trimIndent())

            // 4. xl/workbook.xml
            addZipEntry(zip, "xl/workbook.xml", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                    <sheets>
                        <sheet name="ملخص الفروقات والمطابقة" sheetId="1" r:id="rId1"/>
                        <sheet name="سجل وتفاصيل الجرد (Audit)" sheetId="2" r:id="rId2"/>
                        <sheet name="مسار الجرد الفيزيائي على الرفوف" sheetId="3" r:id="rId3"/>
                        <sheet name="أصناف غير معرّفة" sheetId="4" r:id="rId4"/>
                    </sheets>
                </workbook>
            """.trimIndent())

            // 5. xl/styles.xml (Professional Enterprise Palette)
            addZipEntry(zip, "xl/styles.xml", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                    <fonts count="7">
                        <font><sz val="11"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="14"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="11"/><color rgb="FF0F172A"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="11"/><color rgb="FFDC2626"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="11"/><color rgb="FF059669"/><name val="Segoe UI"/></font>
                    </fonts>
                    <fills count="9">
                        <fill><patternFill patternType="none"/></fill>
                        <fill><patternFill patternType="gray125"/></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FF059669"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FF1E293B"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FF0F172A"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FFE0F2FE"/></patternFill></fill>
                    </fills>
                    <borders count="2">
                        <border><left/><right/><top/><bottom/></border>
                        <border>
                            <left style="thin"><color rgb="FFCBD5E1"/></left>
                            <right style="thin"><color rgb="FFCBD5E1"/></right>
                            <top style="thin"><color rgb="FFCBD5E1"/></top>
                            <bottom style="thin"><color rgb="FFCBD5E1"/></bottom>
                        </border>
                    </borders>
                    <cellStyleXfs count="1">
                        <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
                    </cellStyleXfs>
                    <cellXfs count="12">
                        <!-- 0: Normal cell -->
                        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
                        <!-- 1: Emerald Table Header -->
                        <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
                        <!-- 2: Dark Slate Table Header -->
                        <xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
                        <!-- 3: Main Title Banner -->
                        <xf numFmtId="0" fontId="2" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
                        <!-- 4: Subtitle Banner -->
                        <xf numFmtId="0" fontId="3" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
                        <!-- 5: Metadata Label Cell -->
                        <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
                        <!-- 6: Metadata Value Cell -->
                        <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
                        <!-- 7: KPI Card Header -->
                        <xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
                        <!-- 8: KPI Card Value -->
                        <xf numFmtId="0" fontId="4" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
                        <!-- 9: Shortage Red Alert Cell -->
                        <xf numFmtId="0" fontId="5" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
                        <!-- 10: Surplus Green Soft Cell -->
                        <xf numFmtId="0" fontId="6" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
                        <!-- 11: Totals Row -->
                        <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
                    </cellXfs>
                </styleSheet>
            """.trimIndent())

            // 6. Sheet 1: Summary & Variance with Executive Header
            val s1Xml = buildSheet1Xml(metadata, consolidated)
            addZipEntry(zip, "xl/worksheets/sheet1.xml", s1Xml)

            // 7. Sheet 2: Audit Trail (Detailed Scans)
            val s2Xml = buildSheet2Xml(metadata, rawScans)
            addZipEntry(zip, "xl/worksheets/sheet2.xml", s2Xml)

            // 8. Sheet 3: Physical Shelf Walk
            val s3Xml = buildShelfWalkSheetXml(metadata, rawScans)
            addZipEntry(zip, "xl/worksheets/sheet3.xml", s3Xml)

            // 9. Sheet 4: Unknowns
            val s4Xml = buildSheet4Xml(metadata, unknowns)
            addZipEntry(zip, "xl/worksheets/sheet4.xml", s4Xml)
        }
    }

    private fun buildSheet1Xml(metadata: InventoryReportMetadata, items: List<ConsolidatedItem>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")

        // Custom column widths to ensure perfect readability
        sb.append("<cols>\n")
        sb.append("<col min=\"1\" max=\"1\" width=\"18\" customWidth=\"1\"/>\n") // A: Barcode
        sb.append("<col min=\"2\" max=\"2\" width=\"16\" customWidth=\"1\"/>\n") // B: Code
        sb.append("<col min=\"3\" max=\"3\" width=\"34\" customWidth=\"1\"/>\n") // C: Name Ar
        sb.append("<col min=\"4\" max=\"4\" width=\"28\" customWidth=\"1\"/>\n") // D: Name En
        sb.append("<col min=\"5\" max=\"5\" width=\"18\" customWidth=\"1\"/>\n") // E: Counted Qty
        sb.append("<col min=\"6\" max=\"6\" width=\"22\" customWidth=\"1\"/>\n") // F: System Qty
        sb.append("<col min=\"7\" max=\"7\" width=\"16\" customWidth=\"1\"/>\n") // G: Variance
        sb.append("<col min=\"8\" max=\"8\" width=\"16\" customWidth=\"1\"/>\n") // H: Cost Price
        sb.append("<col min=\"9\" max=\"9\" width=\"18\" customWidth=\"1\"/>\n") // I: Var Value
        sb.append("<col min=\"10\" max=\"10\" width=\"16\" customWidth=\"1\"/>\n") // J: List Price
        sb.append("<col min=\"11\" max=\"11\" width=\"20\" customWidth=\"1\"/>\n") // K: Method
        sb.append("</cols>\n")

        sb.append("<sheetData>\n")

        // Calculations
        val totalItemsCount = items.size
        val totalCountedUnits = items.sumOf { it.countedQty }
        val totalSystemUnits = items.sumOf { it.systemQty }
        val netVarianceUnits = totalCountedUnits - totalSystemUnits
        val totalVarianceValue = items.sumOf { it.varianceValue }
        val matchedCount = items.count { it.varianceQty == 0.0 }
        val shortageCount = items.count { it.varianceQty < 0.0 }
        val surplusCount = items.count { it.varianceQty > 0.0 }
        val manualCount = items.count { it.scanMethod == "MANUAL" }
        val accuracyPercent = if (totalItemsCount > 0) (matchedCount.toDouble() / totalItemsCount.toDouble()) * 100.0 else 100.0

        // ── ROW 1: Main Corporate Header ─────────────────────────────────────────
        sb.append("<row r=\"1\" ht=\"28\" customHeight=\"1\">\n")
        sb.append("<c r=\"A1\" s=\"3\" t=\"inlineStr\"><is><t>🏢 شركة العسلي المحدودة — تقرير جرد ومطابقة المخزون الميداني مع نظام Odoo ERP</t></is></c>\n")
        sb.append("</row>\n")

        // ── ROW 2: Subtitle Banner ───────────────────────────────────────────────
        sb.append("<row r=\"2\" ht=\"20\" customHeight=\"1\">\n")
        sb.append("<c r=\"A2\" s=\"4\" t=\"inlineStr\"><is><t>نظام FastInventory الذكي v1.05 • تقرير المطابقة التنفيذية والفروقات المخزنية الرسمية</t></is></c>\n")
        sb.append("</row>\n")

        // ── ROW 3: Spacer ────────────────────────────────────────────────────────
        sb.append("<row r=\"3\" ht=\"10\" customHeight=\"1\"/>\n")

        // ── ROW 4: Metadata Row 1 (Showroom Identification) ─────────────────────
        sb.append("<row r=\"4\" ht=\"22\" customHeight=\"1\">\n")
        sb.append("<c r=\"A4\" s=\"5\" t=\"inlineStr\"><is><t>اسم المعرض / المستودع:</t></is></c>\n")
        sb.append("<c r=\"B4\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.warehouseName)}</t></is></c>\n")
        sb.append("<c r=\"C4\" s=\"5\" t=\"inlineStr\"><is><t>رقم المعرض في Odoo (ID):</t></is></c>\n")
        sb.append("<c r=\"D4\" s=\"6\" t=\"inlineStr\"><is><t>${if (metadata.warehouseId > 0) metadata.warehouseId.toString() else "المخزون العام"}</t></is></c>\n")
        sb.append("<c r=\"E4\" s=\"5\" t=\"inlineStr\"><is><t>كود المعرض المختصر:</t></is></c>\n")
        sb.append("<c r=\"F4\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.warehouseCode.ifBlank { "WH" })}</t></is></c>\n")
        sb.append("<c r=\"G4\" s=\"5\" t=\"inlineStr\"><is><t>موقع التخزين (Location):</t></is></c>\n")
        sb.append("<c r=\"H4\" s=\"6\" t=\"inlineStr\"><is><t>${if (metadata.lotStockId > 0) "Location ID: " + metadata.lotStockId else "الافتراضي"}</t></is></c>\n")
        sb.append("<c r=\"I4\" s=\"5\" t=\"inlineStr\"><is><t>حالة المطابقة:</t></is></c>\n")
        sb.append("<c r=\"J4\" s=\"${if (netVarianceUnits == 0.0) "10" else "9"}\" t=\"inlineStr\"><is><t>${if (netVarianceUnits == 0.0) "مطابق تماماً 🟢" else "يوجد فروقات ⚠️"}</t></is></c>\n")
        sb.append("<c r=\"K4\" s=\"0\"/>\n")
        sb.append("</row>\n")

        // ── ROW 5: Metadata Row 2 (Session Details & Timestamps) ──────────────────
        sb.append("<row r=\"5\" ht=\"22\" customHeight=\"1\">\n")
        sb.append("<c r=\"A5\" s=\"5\" t=\"inlineStr\"><is><t>اسم جلسة الجرد:</t></is></c>\n")
        sb.append("<c r=\"B5\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.sessionName)}</t></is></c>\n")
        sb.append("<c r=\"C5\" s=\"5\" t=\"inlineStr\"><is><t>تاريخ بدء الجرد:</t></is></c>\n")
        sb.append("<c r=\"D5\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.createdAt)}</t></is></c>\n")
        sb.append("<c r=\"E5\" s=\"5\" t=\"inlineStr\"><is><t>تاريخ استخراج التقرير:</t></is></c>\n")
        sb.append("<c r=\"F5\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.exportTimestamp)}</t></is></c>\n")
        sb.append("<c r=\"G5\" s=\"5\" t=\"inlineStr\"><is><t>نطاق الجرد (المنطقة/الرف):</t></is></c>\n")
        sb.append("<c r=\"H5\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.zoneName)}</t></is></c>\n")
        sb.append("<c r=\"I5\" s=\"5\" t=\"inlineStr\"><is><t>الجهاز / المدقق المسؤول:</t></is></c>\n")
        sb.append("<c r=\"J5\" s=\"6\" t=\"inlineStr\"><is><t>${xmlEscape(metadata.deviceName)}</t></is></c>\n")
        sb.append("<c r=\"K5\" s=\"0\"/>\n")
        sb.append("</row>\n")

        // ── ROW 6: Spacer ────────────────────────────────────────────────────────
        sb.append("<row r=\"6\" ht=\"10\" customHeight=\"1\"/>\n")

        // ── ROW 7: Executive KPI Cards Headers ──────────────────────────────────
        sb.append("<row r=\"7\" ht=\"22\" customHeight=\"1\">\n")
        sb.append("<c r=\"A7\" s=\"7\" t=\"inlineStr\"><is><t>إجمالي الأصناف</t></is></c>\n")
        sb.append("<c r=\"B7\" s=\"7\" t=\"inlineStr\"><is><t>الحبات الفعلية</t></is></c>\n")
        sb.append("<c r=\"C7\" s=\"7\" t=\"inlineStr\"><is><t>رصيد Odoo بالمعرض</t></is></c>\n")
        sb.append("<c r=\"D7\" s=\"7\" t=\"inlineStr\"><is><t>صافي فرق الحبات</t></is></c>\n")
        sb.append("<c r=\"E7\" s=\"7\" t=\"inlineStr\"><is><t>قيمة الفروقات (ر.س)</t></is></c>\n")
        sb.append("<c r=\"F7\" s=\"7\" t=\"inlineStr\"><is><t>نسبة دقة الجرد</t></is></c>\n")
        sb.append("<c r=\"G7\" s=\"7\" t=\"inlineStr\"><is><t>أصناف مطابقة 100%</t></is></c>\n")
        sb.append("<c r=\"H7\" s=\"7\" t=\"inlineStr\"><is><t>أصناف بها عجز (نقص)</t></is></c>\n")
        sb.append("<c r=\"I7\" s=\"7\" t=\"inlineStr\"><is><t>أصناف بها فائض</t></is></c>\n")
        sb.append("<c r=\"J7\" s=\"7\" t=\"inlineStr\"><is><t>أصناف يدوية</t></is></c>\n")
        sb.append("<c r=\"K7\" s=\"7\" t=\"inlineStr\"><is><t>الاعتماد الإداري</t></is></c>\n")
        sb.append("</row>\n")

        // ── ROW 8: Executive KPI Cards Values ───────────────────────────────────
        sb.append("<row r=\"8\" ht=\"24\" customHeight=\"1\">\n")
        sb.append("<c r=\"A8\" s=\"8\" t=\"inlineStr\"><is><t>${totalItemsCount} صنف</t></is></c>\n")
        sb.append("<c r=\"B8\" s=\"8\" t=\"inlineStr\"><is><t>${String.format(Locale.US, "%.0f", totalCountedUnits)} حبة</t></is></c>\n")
        sb.append("<c r=\"C8\" s=\"8\" t=\"inlineStr\"><is><t>${String.format(Locale.US, "%.0f", totalSystemUnits)} حبة</t></is></c>\n")
        sb.append("<c r=\"D8\" s=\"${if (netVarianceUnits < 0) "9" else if (netVarianceUnits > 0) "10" else "8"}\" t=\"inlineStr\"><is><t>${if (netVarianceUnits > 0) "+${String.format(Locale.US, "%.0f", netVarianceUnits)}" else String.format(Locale.US, "%.0f", netVarianceUnits)} حبة</t></is></c>\n")
        sb.append("<c r=\"E8\" s=\"${if (totalVarianceValue < 0) "9" else if (totalVarianceValue > 0) "10" else "8"}\" t=\"inlineStr\"><is><t>${String.format(Locale.US, "%.2f", totalVarianceValue)} ر.س</t></is></c>\n")
        sb.append("<c r=\"F8\" s=\"8\" t=\"inlineStr\"><is><t>${String.format(Locale.US, "%.1f", accuracyPercent)} %</t></is></c>\n")
        sb.append("<c r=\"G8\" s=\"10\" t=\"inlineStr\"><is><t>${matchedCount} صنف</t></is></c>\n")
        sb.append("<c r=\"H8\" s=\"9\" t=\"inlineStr\"><is><t>${shortageCount} صنف</t></is></c>\n")
        sb.append("<c r=\"I8\" s=\"10\" t=\"inlineStr\"><is><t>${surplusCount} صنف</t></is></c>\n")
        sb.append("<c r=\"J8\" s=\"8\" t=\"inlineStr\"><is><t>${manualCount} صنف</t></is></c>\n")
        sb.append("<c r=\"K8\" s=\"8\" t=\"inlineStr\"><is><t>تدقيق معتمد</t></is></c>\n")
        sb.append("</row>\n")

        // ── ROW 9: Spacer ────────────────────────────────────────────────────────
        sb.append("<row r=\"9\" ht=\"12\" customHeight=\"1\"/>\n")

        // ── ROW 10: Table Column Headers ─────────────────────────────────────────
        val headers = listOf(
            "الباركود",
            "كود الصنف",
            "اسم المنتج بالعربي",
            "اسم المنتج بالإنجليزي",
            "الكمية المحصورة (الفعلي)",
            "رصيد ${xmlEscape(metadata.warehouseName)} في Odoo",
            "فرق الجرد",
            "سعر التكلفة",
            "قيمة الفرق (ر.س)",
            "سعر البيع",
            "طريقة الإدخال"
        )

        sb.append("<row r=\"10\" ht=\"25\" customHeight=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 10\" s=\"2\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        // ── ROWS 11+: Item Data ──────────────────────────────────────────────────
        var rowIdx = 11
        for (item in items) {
            val methodLabel = if (item.scanMethod == "MANUAL") "إدخال يدوي ✏️" else "مسح ليزر/كاميرا ⚡"
            val varStyle = if (item.varianceQty < 0.0) "9" else if (item.varianceQty > 0.0) "10" else "0"

            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.barcode)}</t></is></c>\n")
            sb.append("<c r=\"B$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.defaultCode)}</t></is></c>\n")
            sb.append("<c r=\"C$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.nameAr)}</t></is></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.nameEn)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\" s=\"$varStyle\"><v>${item.countedQty}</v></c>\n")
            sb.append("<c r=\"F$rowIdx\"><v>${item.systemQty}</v></c>\n")
            sb.append("<c r=\"G$rowIdx\" s=\"$varStyle\"><v>${item.varianceQty}</v></c>\n")
            sb.append("<c r=\"H$rowIdx\"><v>${item.costPrice}</v></c>\n")
            sb.append("<c r=\"I$rowIdx\" s=\"$varStyle\"><v>${String.format(Locale.US, "%.2f", item.varianceValue)}</v></c>\n")
            sb.append("<c r=\"J$rowIdx\"><v>${item.listPrice}</v></c>\n")
            sb.append("<c r=\"K$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(methodLabel)}</t></is></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        // ── Grand Totals Row ─────────────────────────────────────────────────────
        val totRow = rowIdx
        sb.append("<row r=\"$totRow\" ht=\"24\" customHeight=\"1\">\n")
        sb.append("<c r=\"A$totRow\" s=\"11\" t=\"inlineStr\"><is><t>الإجمالي الكلي (Grand Totals)</t></is></c>\n")
        sb.append("<c r=\"B$totRow\" s=\"11\"/>\n")
        sb.append("<c r=\"C$totRow\" s=\"11\"/>\n")
        sb.append("<c r=\"D$totRow\" s=\"11\"/>\n")
        sb.append("<c r=\"E$totRow\" s=\"11\"><v>${totalCountedUnits}</v></c>\n")
        sb.append("<c r=\"F$totRow\" s=\"11\"><v>${totalSystemUnits}</v></c>\n")
        sb.append("<c r=\"G$totRow\" s=\"${if (netVarianceUnits < 0) "9" else if (netVarianceUnits > 0) "10" else "11"}\"><v>${netVarianceUnits}</v></c>\n")
        sb.append("<c r=\"H$totRow\" s=\"11\" t=\"inlineStr\"><is><t>-</t></is></c>\n")
        sb.append("<c r=\"I$totRow\" s=\"${if (totalVarianceValue < 0) "9" else if (totalVarianceValue > 0) "10" else "11"}\"><v>${String.format(Locale.US, "%.2f", totalVarianceValue)}</v></c>\n")
        sb.append("<c r=\"J$totRow\" s=\"11\" t=\"inlineStr\"><is><t>-</t></is></c>\n")
        sb.append("<c r=\"K$totRow\" s=\"11\" t=\"inlineStr\"><is><t>-</t></is></c>\n")
        sb.append("</row>\n")

        // ── Sign-off & Committee Approvals Block ───────────────────────────────────
        val sig1 = totRow + 2
        val sig2 = totRow + 3
        sb.append("<row r=\"${totRow + 1}\" ht=\"10\" customHeight=\"1\"/>\n")
        sb.append("<row r=\"$sig1\" ht=\"22\" customHeight=\"1\">\n")
        sb.append("<c r=\"A$sig1\" s=\"5\" t=\"inlineStr\"><is><t>مسؤول الجرد الميداني:</t></is></c>\n")
        sb.append("<c r=\"B$sig1\" s=\"6\" t=\"inlineStr\"><is><t>............................................</t></is></c>\n")
        sb.append("<c r=\"E$sig1\" s=\"5\" t=\"inlineStr\"><is><t>مدير المعرض / المستودع:</t></is></c>\n")
        sb.append("<c r=\"F$sig1\" s=\"6\" t=\"inlineStr\"><is><t>............................................</t></is></c>\n")
        sb.append("<c r=\"I$sig1\" s=\"5\" t=\"inlineStr\"><is><t>مراقب الحسابات والمخزون:</t></is></c>\n")
        sb.append("<c r=\"J$sig1\" s=\"6\" t=\"inlineStr\"><is><t>............................................</t></is></c>\n")
        sb.append("</row>\n")

        sb.append("<row r=\"$sig2\" ht=\"20\" customHeight=\"1\">\n")
        sb.append("<c r=\"A$sig2\" s=\"5\" t=\"inlineStr\"><is><t>التوقيع / التاريخ:</t></is></c>\n")
        sb.append("<c r=\"B$sig2\" s=\"6\" t=\"inlineStr\"><is><t>التاريخ: .... / .... / ........  التوقيع: ..........</t></is></c>\n")
        sb.append("<c r=\"E$sig2\" s=\"5\" t=\"inlineStr\"><is><t>التوقيع / التاريخ:</t></is></c>\n")
        sb.append("<c r=\"F$sig2\" s=\"6\" t=\"inlineStr\"><is><t>التاريخ: .... / .... / ........  التوقيع: ..........</t></is></c>\n")
        sb.append("<c r=\"I$sig2\" s=\"5\" t=\"inlineStr\"><is><t>التوقيع / التاريخ:</t></is></c>\n")
        sb.append("<c r=\"J$sig2\" s=\"6\" t=\"inlineStr\"><is><t>التاريخ: .... / .... / ........  التوقيع: ..........</t></is></c>\n")
        sb.append("</row>\n")

        sb.append("</sheetData>\n")

        // Merged Cells for Title Banners
        sb.append("<mergeCells count=\"2\">\n")
        sb.append("<mergeCell ref=\"A1:K1\"/>\n")
        sb.append("<mergeCell ref=\"A2:K2\"/>\n")
        sb.append("</mergeCells>\n")

        sb.append("</worksheet>")
        return sb.toString()
    }

    private fun buildSheet2Xml(metadata: InventoryReportMetadata, scans: List<ScanRecord>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")

        sb.append("<cols>\n")
        sb.append("<col min=\"1\" max=\"1\" width=\"12\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"2\" max=\"2\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"3\" max=\"3\" width=\"14\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"4\" max=\"4\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"5\" max=\"5\" width=\"16\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"6\" max=\"6\" width=\"34\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"7\" max=\"7\" width=\"14\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"8\" max=\"8\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"9\" max=\"9\" width=\"24\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"10\" max=\"10\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"11\" max=\"11\" width=\"20\" customWidth=\"1\"/>\n")
        sb.append("</cols>\n")

        sb.append("<sheetData>\n")

        // Top Banner
        sb.append("<row r=\"1\" ht=\"25\" customHeight=\"1\">\n")
        sb.append("<c r=\"A1\" s=\"3\" t=\"inlineStr\"><is><t>📋 سجل وتفاصيل الجرد الميداني (Audit Trail) — معرض: ${xmlEscape(metadata.warehouseName)} (ID: ${metadata.warehouseId}) — تاريخ: ${xmlEscape(metadata.exportTimestamp)}</t></is></c>\n")
        sb.append("</row>\n")

        val headers = listOf(
            "تسلسل المسح في الرف (#)",
            "المنطقة / الرف",
            "مستوى الرف",
            "الباركود",
            "كود الصنف",
            "اسم المنتج",
            "الكمية",
            "طريقة الإدخال",
            "نوع المسح",
            "اسم الجهاز / الموظف",
            "التوقيت"
        )
        sb.append("<row r=\"2\" ht=\"25\" customHeight=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 2\" s=\"1\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        var rowIdx = 3
        for (s in scans) {
            val methodDesc = when (s.scanMethod) {
                "MANUAL" -> "إدخال يدوي ✏️"
                "OVERRIDE" -> "تعديل كمية 🔄"
                else -> "مسح ليزر/كاميرا ⚡"
            }
            val pkgDesc = if (s.isPackaging) "كرتون (${s.packagingQty} حبة) - ${s.packagingName}" else "مفرد"
            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\"><v>${s.shelfSeq}</v></c>\n")
            sb.append("<c r=\"B$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.zoneName)}</t></is></c>\n")
            sb.append("<c r=\"C$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.shelfLevel.ifBlank { "-" })}</t></is></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.barcode)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.defaultCode)}</t></is></c>\n")
            sb.append("<c r=\"F$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.nameAr)}</t></is></c>\n")
            sb.append("<c r=\"G$rowIdx\"><v>${s.qty}</v></c>\n")
            sb.append("<c r=\"H$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(methodDesc)}</t></is></c>\n")
            sb.append("<c r=\"I$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(pkgDesc)}</t></is></c>\n")
            sb.append("<c r=\"J$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.deviceName)}</t></is></c>\n")
            sb.append("<c r=\"K$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.timestamp)}</t></is></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        sb.append("</sheetData>\n")
        sb.append("<mergeCells count=\"1\">\n<mergeCell ref=\"A1:K1\"/>\n</mergeCells>\n")
        sb.append("</worksheet>")
        return sb.toString()
    }

    private fun buildShelfWalkSheetXml(metadata: InventoryReportMetadata, scans: List<ScanRecord>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")

        sb.append("<cols>\n")
        sb.append("<col min=\"1\" max=\"1\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"2\" max=\"2\" width=\"14\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"3\" max=\"3\" width=\"14\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"4\" max=\"4\" width=\"34\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"5\" max=\"5\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"6\" max=\"6\" width=\"16\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"7\" max=\"7\" width=\"14\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"8\" max=\"8\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"9\" max=\"9\" width=\"20\" customWidth=\"1\"/>\n")
        sb.append("</cols>\n")

        sb.append("<sheetData>\n")

        // Top Banner
        sb.append("<row r=\"1\" ht=\"25\" customHeight=\"1\">\n")
        sb.append("<c r=\"A1\" s=\"3\" t=\"inlineStr\"><is><t>🚶 مسار الجرد الفيزيائي على الرفوف (Physical Shelf Walk) — معرض: ${xmlEscape(metadata.warehouseName)} (ID: ${metadata.warehouseId}) — تاريخ: ${xmlEscape(metadata.exportTimestamp)}</t></is></c>\n")
        sb.append("</row>\n")

        val headers = listOf(
            "الرف / المنطقة",
            "ترتيب الصنف في الرف",
            "مستوى الرف",
            "اسم الصنف المحصور",
            "الباركود",
            "كود الصنف",
            "الكمية المحصورة",
            "طريقة الإدخال",
            "توقيت المسح"
        )
        sb.append("<row r=\"2\" ht=\"25\" customHeight=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 2\" s=\"2\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        val sortedScans = scans.sortedWith(compareBy({ it.zoneName }, { it.shelfSeq }, { it.id }))

        var rowIdx = 3
        for (s in sortedScans) {
            val methodDesc = when (s.scanMethod) {
                "MANUAL" -> "إدخال يدوي ✏️"
                "OVERRIDE" -> "تعديل كمية 🔄"
                else -> "مسح ليزر ⚡"
            }
            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.zoneName)}</t></is></c>\n")
            sb.append("<c r=\"B$rowIdx\"><v>${s.shelfSeq}</v></c>\n")
            sb.append("<c r=\"C$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.shelfLevel.ifBlank { "-" })}</t></is></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.nameAr)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.barcode)}</t></is></c>\n")
            sb.append("<c r=\"F$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.defaultCode)}</t></is></c>\n")
            sb.append("<c r=\"G$rowIdx\"><v>${s.qty}</v></c>\n")
            sb.append("<c r=\"H$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(methodDesc)}</t></is></c>\n")
            sb.append("<c r=\"I$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.timestamp)}</t></is></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        sb.append("</sheetData>\n")
        sb.append("<mergeCells count=\"1\">\n<mergeCell ref=\"A1:I1\"/>\n</mergeCells>\n")
        sb.append("</worksheet>")
        return sb.toString()
    }

    private fun buildSheet4Xml(metadata: InventoryReportMetadata, unknowns: List<ScanRecord>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")

        sb.append("<cols>\n")
        sb.append("<col min=\"1\" max=\"1\" width=\"20\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"2\" max=\"2\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"3\" max=\"3\" width=\"16\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"4\" max=\"4\" width=\"18\" customWidth=\"1\"/>\n")
        sb.append("<col min=\"5\" max=\"5\" width=\"20\" customWidth=\"1\"/>\n")
        sb.append("</cols>\n")

        sb.append("<sheetData>\n")

        // Top Banner
        sb.append("<row r=\"1\" ht=\"25\" customHeight=\"1\">\n")
        sb.append("<c r=\"A1\" s=\"3\" t=\"inlineStr\"><is><t>⚠️ أصناف ممسوحة غير معرّفة في Odoo — معرض: ${xmlEscape(metadata.warehouseName)} — تاريخ: ${xmlEscape(metadata.exportTimestamp)}</t></is></c>\n")
        sb.append("</row>\n")

        val headers = listOf("الباركود غير المعرّف", "المنطقة / الرف", "الكمية المحصورة", "الجهاز", "التوقيت")
        sb.append("<row r=\"2\" ht=\"25\" customHeight=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 2\" s=\"1\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        var rowIdx = 3
        for (u in unknowns) {
            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(u.barcode)}</t></is></c>\n")
            sb.append("<c r=\"B$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(u.zoneName)}</t></is></c>\n")
            sb.append("<c r=\"C$rowIdx\"><v>${u.qty}</v></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(u.deviceName)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(u.timestamp)}</t></is></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        sb.append("</sheetData>\n")
        sb.append("<mergeCells count=\"1\">\n<mergeCell ref=\"A1:E1\"/>\n</mergeCells>\n")
        sb.append("</worksheet>")
        return sb.toString()
    }

    private fun addZipEntry(zip: ZipOutputStream, path: String, content: String) {
        val bytes = content.toByteArray(StandardCharsets.UTF_8)
        val entry = ZipEntry(path)
        zip.putNextEntry(entry)
        zip.write(bytes)
        zip.closeEntry()
    }

    private fun getColumnLetter(colIndex: Int): String {
        var temp = colIndex
        var colName = ""
        while (temp > 0) {
            val rem = (temp - 1) % 26
            colName = ('A'.code + rem).toChar() + colName
            temp = (temp - 1) / 26
        }
        return colName
    }

    private fun xmlEscape(s: String): String {
        return s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;")
    }
}
