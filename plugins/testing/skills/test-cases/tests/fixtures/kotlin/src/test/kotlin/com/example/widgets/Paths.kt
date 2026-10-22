package com.example.widgets

object Paths {
    private const val V1 = "/v1"
    const val WIDGETS = "$V1/{tenantId}/widgets"
    const val WIDGET = "${WIDGETS}/{widgetId}"
    val WIDGET_ARCHIVE = WIDGET + "/archive"
    const val PART_FMT = "/v1/%s/parts/%s"
    const val LEGACY = "/v0/legacy"
    const val UNRESOLVED = "$MISSING/x"

    fun parts(tenant: String) = "$V1/$tenant/parts"
}
