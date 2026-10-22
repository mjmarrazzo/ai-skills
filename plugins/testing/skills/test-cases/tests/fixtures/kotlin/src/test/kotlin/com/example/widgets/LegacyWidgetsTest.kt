package com.example.widgets

import org.junit.jupiter.api.Disabled
import org.junit.jupiter.api.Test

@Disabled
class LegacyWidgetsTest {
    @Test
    fun old() {
        When { get("/v0/legacy") } Then { statusCode(200) }
    }
}
