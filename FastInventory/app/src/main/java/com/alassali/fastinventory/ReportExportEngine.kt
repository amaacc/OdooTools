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
     */
    fun exportSessionReport(
        context: Context,
        sessionName: String,
        zoneName: String,
        items: List<ScanRecord>,
        db: InventoryDatabase
    ): ExportResult {
        val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val cleanName = sessionName.replace("[^a-zA-Z0-9_\\-\\u0600-\\u06FF]".toRegex(), "_")

        val cacheDir = context.cacheDir
        val csvFile = File(cacheDir, "FastInventory_${cleanName}_$dateStamp.csv")
        val xlsxFile = File(cacheDir, "FastInventory_${cleanName}_$dateStamp.xlsx")

        // 1. Build Consolidated Items with System Quantities & Cost
        val consolidatedList = mutableListOf<ConsolidatedItem>()
        val unknownList = mutableListOf<ScanRecord>()

        var totalCounted = 0.0
        var totalSystem = 0.0
        var totalVarianceVal = 0.0

        for (rec in items) {
            val prod = db.getProductByBarcodeOrCode(rec.barcode)
            if (prod == null) {
                unknownList.add(rec)
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
                listPrice = listPrice
            )
            item.zoneCounts[rec.zoneName] = rec.qty
            consolidatedList.add(item)

            totalCounted += rec.qty
            totalSystem += sysQty
            totalVarianceVal += item.varianceValue
        }

        // 2. Write CSV with UTF-8 BOM
        writeCsvReport(csvFile, sessionName, zoneName, consolidatedList, unknownList)

        // 3. Write Pure-Kotlin Multi-Sheet XLSX
        writeXlsxWorkbook(xlsxFile, consolidatedList, unknownList, items)

        val summaryText = """
            📦 ملخص تقرير الجرد والمطابقة:
            • الجلسة: $sessionName
            • المنطقة/الرف: $zoneName
            • عدد الأصناف المحصورة: ${consolidatedList.size}
            • إجمالي الحبات المحصورة: ${String.format(Locale.US, "%.0f", totalCounted)}
            • إجمالي رصيد النظام في أودو: ${String.format(Locale.US, "%.0f", totalSystem)}
            • فرق الكمية الإجمالي: ${String.format(Locale.US, "%.0f", totalCounted - totalSystem)}
            • إجمالي قيمة الفروقات: ${String.format(Locale.US, "%.2f", totalVarianceVal)} ر.س
            • الأصناف غير المعرّفة: ${unknownList.size}
        """.trimIndent()

        return ExportResult(csvFile, xlsxFile, summaryText)
    }

    /**
     * Exports a multi-device consolidated report.
     */
    fun exportConsolidatedReport(
        context: Context,
        reportTitle: String,
        consolidatedMap: Map<String, ConsolidatedItem>,
        rawRecords: List<ScanRecord>
    ): ExportResult {
        val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val cacheDir = context.cacheDir
        val csvFile = File(cacheDir, "Master_Consolidated_Inventory_$dateStamp.csv")
        val xlsxFile = File(cacheDir, "Master_Consolidated_Inventory_$dateStamp.xlsx")

        val consolidatedList = consolidatedMap.values.toList()
        val unknownList = rawRecords.filter { it.nameAr.contains("غير معرّف") || it.defaultCode == "-" }

        var totalCounted = 0.0
        var totalSystem = 0.0
        var totalVarianceVal = 0.0

        for (item in consolidatedList) {
            totalCounted += item.countedQty
            totalSystem += item.systemQty
            totalVarianceVal += item.varianceValue
        }

        writeCsvReport(csvFile, reportTitle, "كافة الأجهزة والمناطق المدمجة", consolidatedList, unknownList)
        writeXlsxWorkbook(xlsxFile, consolidatedList, unknownList, rawRecords)

        val summaryText = """
            🚀 ملخص التقرير المدمج لكافة أجهزة الجرد:
            • العنوان: $reportTitle
            • إجمالي الأصناف المدمجة: ${consolidatedList.size}
            • إجمالي الحبات المحصورة فعلياً: ${String.format(Locale.US, "%.0f", totalCounted)}
            • إجمالي رصيد النظام في Odoo: ${String.format(Locale.US, "%.0f", totalSystem)}
            • صافي فرق الجرد: ${String.format(Locale.US, "%.0f", totalCounted - totalSystem)}
            • القيمة الإجمالية لفروقات الجرد: ${String.format(Locale.US, "%.2f", totalVarianceVal)} ر.س
        """.trimIndent()

        return ExportResult(csvFile, xlsxFile, summaryText)
    }

    private fun writeCsvReport(
        file: File,
        title: String,
        zone: String,
        items: List<ConsolidatedItem>,
        unknowns: List<ScanRecord>
    ) {
        FileOutputStream(file).use { fos ->
            // Write UTF-8 BOM for perfect Excel compatibility
            fos.write(byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()))

            OutputStreamWriter(fos, StandardCharsets.UTF_8).use { writer ->
                writer.append("تقرير الجرد والمطابقة — شركة العسلي التجارية\n")
                writer.append("الجلسة,$title,المنطقة,$zone,تاريخ التصدير,${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())}\n\n")

                // Main Variance Table Header
                writer.append("الباركود,كود الصنف,اسم المنتج بالعربي,اسم المنتج بالإنجليزي,الكمية المحصورة (الفعلي),رصيد النظام (Odoo),فرق الجرد,سعر التكلفة,قيمة الفرق (ر.س),سعر البيع\n")

                for (item in items) {
                    val escNameAr = escapeCsv(item.nameAr)
                    val escNameEn = escapeCsv(item.nameEn)
                    writer.append("${item.barcode},${item.defaultCode},$escNameAr,$escNameEn,${item.countedQty},${item.systemQty},${item.varianceQty},${item.costPrice},${String.format(Locale.US, "%.2f", item.varianceValue)},${item.listPrice}\n")
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
                    <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
                </Relationships>
            """.trimIndent())

            // 4. xl/workbook.xml
            addZipEntry(zip, "xl/workbook.xml", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                    <sheets>
                        <sheet name="ملخص الفروقات والمطابقة" sheetId="1" r:id="rId1"/>
                        <sheet name="سجل وتفاصيل الجرد (Audit)" sheetId="2" r:id="rId2"/>
                        <sheet name="أصناف غير معرّفة" sheetId="3" r:id="rId3"/>
                    </sheets>
                </workbook>
            """.trimIndent())

            // 5. xl/styles.xml (styles for headers, borders, numbers)
            addZipEntry(zip, "xl/styles.xml", """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                    <fonts count="2">
                        <font><sz val="11"/><name val="Segoe UI"/></font>
                        <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>
                    </fonts>
                    <fills count="3">
                        <fill><patternFill patternType="none"/></fill>
                        <fill><patternFill patternType="gray125"/></fill>
                        <fill><patternFill patternType="solid"><fgColor rgb="FF059669"/></patternFill></fill>
                    </fills>
                    <borders count="1">
                        <border><left/><right/><top/><bottom/></border>
                    </borders>
                    <cellStyleXfs count="1">
                        <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
                    </cellStyleXfs>
                    <cellXfs count="2">
                        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
                        <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
                    </cellXfs>
                </styleSheet>
            """.trimIndent())

            // 6. Sheet 1: Summary & Variance
            val s1Xml = buildSheet1Xml(consolidated)
            addZipEntry(zip, "xl/worksheets/sheet1.xml", s1Xml)

            // 7. Sheet 2: Audit Trail
            val s2Xml = buildSheet2Xml(rawScans)
            addZipEntry(zip, "xl/worksheets/sheet2.xml", s2Xml)

            // 8. Sheet 3: Unknowns
            val s3Xml = buildSheet3Xml(unknowns)
            addZipEntry(zip, "xl/worksheets/sheet3.xml", s3Xml)
        }
    }

    private fun buildSheet1Xml(items: List<ConsolidatedItem>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")
        sb.append("<sheetData>\n")

        // Header Row (Row 1, style 1 = emerald header)
        val headers = listOf("الباركود", "كود الصنف", "اسم المنتج بالعربي", "اسم المنتج بالإنجليزي", "الفعلي (المحصور)", "رصيد أودو (النظام)", "فرق الجرد", "سعر التكلفة", "قيمة الفرق (ر.س)", "سعر البيع")
        sb.append("<row r=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 1\" s=\"1\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        // Data Rows
        var rowIdx = 2
        for (item in items) {
            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.barcode)}</t></is></c>\n")
            sb.append("<c r=\"B$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.defaultCode)}</t></is></c>\n")
            sb.append("<c r=\"C$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.nameAr)}</t></is></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(item.nameEn)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\"><v>${item.countedQty}</v></c>\n")
            sb.append("<c r=\"F$rowIdx\"><v>${item.systemQty}</v></c>\n")
            sb.append("<c r=\"G$rowIdx\"><v>${item.varianceQty}</v></c>\n")
            sb.append("<c r=\"H$rowIdx\"><v>${item.costPrice}</v></c>\n")
            sb.append("<c r=\"I$rowIdx\"><v>${String.format(Locale.US, "%.2f", item.varianceValue)}</v></c>\n")
            sb.append("<c r=\"J$rowIdx\"><v>${item.listPrice}</v></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        sb.append("</sheetData>\n</worksheet>")
        return sb.toString()
    }

    private fun buildSheet2Xml(scans: List<ScanRecord>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")
        sb.append("<sheetData>\n")

        val headers = listOf("التوقيت", "اسم الجهاز / الموظف", "المنطقة / الرف", "الباركود", "كود الصنف", "اسم المنتج", "الكمية الممسوحة", "نوع المسح (مفرد/كرتون)")
        sb.append("<row r=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 1\" s=\"1\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        var rowIdx = 2
        for (s in scans) {
            val pkgDesc = if (s.isPackaging) "كرتون (${s.packagingQty} حبة) - ${s.packagingName}" else "مفرد"
            sb.append("<row r=\"$rowIdx\">\n")
            sb.append("<c r=\"A$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.timestamp)}</t></is></c>\n")
            sb.append("<c r=\"B$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.deviceName)}</t></is></c>\n")
            sb.append("<c r=\"C$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.zoneName)}</t></is></c>\n")
            sb.append("<c r=\"D$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.barcode)}</t></is></c>\n")
            sb.append("<c r=\"E$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.defaultCode)}</t></is></c>\n")
            sb.append("<c r=\"F$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(s.nameAr)}</t></is></c>\n")
            sb.append("<c r=\"G$rowIdx\"><v>${s.qty}</v></c>\n")
            sb.append("<c r=\"H$rowIdx\" t=\"inlineStr\"><is><t>${xmlEscape(pkgDesc)}</t></is></c>\n")
            sb.append("</row>\n")
            rowIdx++
        }

        sb.append("</sheetData>\n</worksheet>")
        return sb.toString()
    }

    private fun buildSheet3Xml(unknowns: List<ScanRecord>): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        sb.append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n")
        sb.append("<sheetViews><sheetView rightToLeft=\"1\" workbookViewId=\"0\"/></sheetViews>\n")
        sb.append("<sheetData>\n")

        val headers = listOf("الباركود غير المعرّف", "المنطقة / الرف", "الكمية المحصورة", "الجهاز", "التوقيت")
        sb.append("<row r=\"1\">\n")
        headers.forEachIndexed { i, h ->
            val colLetter = getColumnLetter(i + 1)
            sb.append("<c r=\"$colLetter 1\" s=\"1\" t=\"inlineStr\"><is><t>${xmlEscape(h)}</t></is></c>\n")
        }
        sb.append("</row>\n")

        var rowIdx = 2
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

        sb.append("</sheetData>\n</worksheet>")
        return sb.toString()
    }

    private fun addZipEntry(zip: ZipOutputStream, entryName: String, content: String) {
        zip.putNextEntry(ZipEntry(entryName))
        val bytes = content.toByteArray(StandardCharsets.UTF_8)
        zip.write(bytes)
        zip.closeEntry()
    }

    private fun getColumnLetter(colIndex: Int): String {
        var n = colIndex
        val sb = StringBuilder()
        while (n > 0) {
            val rem = (n - 1) % 26
            sb.append(('A'.code + rem).toChar())
            n = (n - 1) / 26
        }
        return sb.reverse().toString()
    }

    private fun xmlEscape(str: String): String {
        return str.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;")
    }
}
