package com.alassali.showroomchecker

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object ShowroomManager {

    private const val PREFS_NAME = "showroom_checker_prefs"
    private const val KEY_ACTIVE_SHOWROOM_ID = "active_showroom_id"
    private const val KEY_ACTIVE_SHOWROOM_NAME = "active_showroom_name"
    private const val KEY_ACTIVE_SHOWROOM_CODE = "active_showroom_code"
    private const val KEY_ACTIVE_SHOWROOM_LOC_ID = "active_showroom_loc_id"
    private const val KEY_ACTIVE_SHOWROOM_POS_IDS = "active_showroom_pos_ids"
    private const val KEY_CACHED_SHOWROOMS = "cached_showrooms_json"
    private const val KEY_SALES_PERIOD = "sales_period"
    private const val KEY_NEED_MONTHS = "need_months"

    const val DEFAULT_SALES_PERIOD = "this_year"
    const val DEFAULT_NEED_MONTHS = 2

    // Default Al-Assali 32 active POS showrooms with locationId and posConfigIds
    val DEFAULT_SHOWROOMS = listOf(
        Showroom(48, "معرض الشربتلي", "101", 301, listOf(1)),
        Showroom(49, "معرض البطاطي", "102", 308, listOf(2, 50)),
        Showroom(50, "معرض الاسنوي", "103", 315, listOf(3)),
        Showroom(51, "معرض الذهب", "104", 322, listOf(5)),
        Showroom(52, "معرض باناجة", "105", 329, listOf(6)),
        Showroom(53, "معرض الصفاء", "106", 336, listOf(7, 63)),
        Showroom(54, "معرض الاوقاف", "107", 343, listOf(8)),
        Showroom(60, "معرض البوادي", "112", 385, listOf(13)),
        Showroom(63, "معرض مكة الستين", "115", 406, listOf(16, 52)),
        Showroom(64, "معرض مكة الشرائع", "116", 413, listOf(17, 61)),
        Showroom(66, "معرض الطايف", "118", 427, listOf(19, 57, 58)),
        Showroom(67, "معرض ينبع", "119", 434, listOf(20)),
        Showroom(68, "معرض الحمدانية", "120", 441, listOf(21, 62)),
        Showroom(69, "معرض الدراجة MS", "121", 448, listOf(22)),
        Showroom(70, "معرض البوادي MS", "122", 455, listOf(23)),
        Showroom(71, "معرض قربان MS", "123", 462, listOf(24)),
        Showroom(91, "معرض مكة العزيزة", "125", 601, listOf(43, 53, 54)),
        Showroom(95, "معرض الوزرية", "127", 632, listOf(45)),
        Showroom(100, "سوق الشاطئ", "128", 677, listOf(46, 47, 48, 49)),
        Showroom(106, "معرض المكرونة 2", "129", 739, listOf(55)),
        Showroom(72, "معرض الخزان", "130", 469, listOf(25)),
        Showroom(74, "معرض المعقلية MS", "132", 483, listOf(27)),
        Showroom(76, "معرض الدمام", "140", 497, listOf(29)),
        Showroom(78, "معرض الاحساء الهفوف", "142", 511, listOf(31)),
        Showroom(79, "معرض الحب MS", "143", 518, listOf(32)),
        Showroom(83, "معرض العسكرية", "151", 546, listOf(36)),
        Showroom(84, "معرض خميس البلد", "152", 553, listOf(37)),
        Showroom(85, "معرض محايل عسير", "153", 560, listOf(38)),
        Showroom(87, "معرض جيزان الاسرة", "155", 574, listOf(40)),
        Showroom(112, "معرض صبيا", "157", 848, listOf(65)),
        Showroom(139, "فرع مس برتي", "MSPRT", 1122, listOf(73)),
        Showroom(138, "فرع النورية", "NORYA", 1041, listOf(72))
    )

    fun getActiveShowroom(context: Context): Showroom? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val id = prefs.getInt(KEY_ACTIVE_SHOWROOM_ID, -1)
        if (id <= 0) return null

        val name = prefs.getString(KEY_ACTIVE_SHOWROOM_NAME, "") ?: ""
        val code = prefs.getString(KEY_ACTIVE_SHOWROOM_CODE, "") ?: ""
        val locId = prefs.getInt(KEY_ACTIVE_SHOWROOM_LOC_ID, -1)
        val posStr = prefs.getString(KEY_ACTIVE_SHOWROOM_POS_IDS, "") ?: ""
        val posIds = if (posStr.isNotBlank()) {
            posStr.split(",").mapNotNull { it.trim().toIntOrNull() }
        } else {
            DEFAULT_SHOWROOMS.find { it.id == id }?.posConfigIds ?: emptyList()
        }

        return if (locId > 0 && name.isNotBlank()) {
            Showroom(id, name, code, locId, posIds)
        } else null
    }

    fun setActiveShowroom(context: Context, showroom: Showroom) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().apply {
            putInt(KEY_ACTIVE_SHOWROOM_ID, showroom.id)
            putString(KEY_ACTIVE_SHOWROOM_NAME, showroom.name)
            putString(KEY_ACTIVE_SHOWROOM_CODE, showroom.code)
            putInt(KEY_ACTIVE_SHOWROOM_LOC_ID, showroom.locationId)
            putString(KEY_ACTIVE_SHOWROOM_POS_IDS, showroom.posConfigIds.joinToString(","))
        }.apply()
    }

    fun getAllShowrooms(context: Context): List<Showroom> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val cachedJson = prefs.getString(KEY_CACHED_SHOWROOMS, null)

        if (!cachedJson.isNullOrBlank()) {
            try {
                val array = JSONArray(cachedJson)
                val list = mutableListOf<Showroom>()
                for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    val posArray = obj.optJSONArray("posConfigIds")
                    val posList = mutableListOf<Int>()
                    if (posArray != null) {
                        for (p in 0 until posArray.length()) {
                            posList.add(posArray.getInt(p))
                        }
                    }
                    list.add(
                        Showroom(
                            id = obj.getInt("id"),
                            name = obj.getString("name"),
                            code = obj.optString("code", ""),
                            locationId = obj.getInt("locationId"),
                            posConfigIds = if (posList.isNotEmpty()) posList else (DEFAULT_SHOWROOMS.find { it.id == obj.getInt("id") }?.posConfigIds ?: emptyList())
                        )
                    )
                }
                if (list.isNotEmpty()) return list
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
        return DEFAULT_SHOWROOMS
    }

    fun saveShowroomsCache(context: Context, showrooms: List<Showroom>) {
        val array = JSONArray()
        for (s in showrooms) {
            val obj = JSONObject().apply {
                put("id", s.id)
                put("name", s.name)
                put("code", s.code)
                put("locationId", s.locationId)
                put("posConfigIds", JSONArray(s.posConfigIds))
            }
            array.put(obj)
        }
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_CACHED_SHOWROOMS, array.toString()).apply()
    }

    fun getSalesPeriod(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_SALES_PERIOD, DEFAULT_SALES_PERIOD) ?: DEFAULT_SALES_PERIOD
    }

    fun setSalesPeriod(context: Context, period: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_SALES_PERIOD, period).apply()
    }

    fun getNeedMonths(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getInt(KEY_NEED_MONTHS, DEFAULT_NEED_MONTHS)
    }

    fun setNeedMonths(context: Context, months: Int) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putInt(KEY_NEED_MONTHS, months).apply()
    }
}
