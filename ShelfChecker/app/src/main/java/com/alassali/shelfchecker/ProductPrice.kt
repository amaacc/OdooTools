package com.alassali.shelfchecker

data class ProductPrice(
    val barcode: String,
    val price: Double,
    val isTaxable: Boolean,
    val taxRate: Double
)
