package com.example.widgets

abstract class WidgetTestBase {
    fun createWidgetViaHelper() = When { post(Paths.WIDGETS) }
}
