package com.example.widgets

import org.apache.http.HttpStatus
import org.junit.jupiter.api.Disabled
import org.junit.jupiter.api.DynamicTest.dynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory

class WidgetsPostTest : WidgetTestBase() {

    @Test
    fun createWidget_ok() {
        When { post(Paths.WIDGETS) } Then { statusCode(201) }
    }

    @Test
    fun createWidget_nameTooLong() {
        When { post(Paths.WIDGETS) } Then { statusCode(HttpStatus.SC_BAD_REQUEST) }
    }

    @Disabled("not ready")
    @Test
    fun createWidget_disabled() {
        When { post(Paths.WIDGETS) } Then { statusCode(201) }
    }

    @ManualTest
    @Test
    fun createWidget_manual() {
        When { post(Paths.WIDGETS) } Then { statusCode(201) }
    }

    @Test
    fun createWidget_empty() {
        // pending
    }

    @Test
    fun createWidget_noAssert() {
        When { post(Paths.WIDGETS) }
    }

    @Test
    fun createWidget_teapot() {
        When { post(Paths.WIDGETS) } Then { statusCode(418) }
    }

    @TestFactory
    fun createWidget_invalidNames(): Stream<DynamicTest> {
        return listOf("", " ").stream().map { name ->
            dynamicTest("name '$name'") {
                Given { body(mapOf("name" to name)) } When { post(Paths.WIDGETS) } Then { statusCode(400) }
            }
        }
    }

    @Test
    fun `archive returns 200`() {
        When { post(Paths.WIDGET_ARCHIVE) } Then { statusCode(200) }
    }

    @Test
    fun createWidget_viaHelper() {
        createWidgetViaHelper().then().statusCode(201)
    }

    @Test
    fun getWidget_braceInString() {
        val s = "}{"
        /* } */
        When { get(Paths.WIDGET) } Then { statusCode(404) }
    }

    @Test
    fun createPart_fn() {
        When { post(Paths.parts("t1")) } Then { statusCode(201) }
    }

    @Test fun getWidget_sameLine() {
        val trace = headers.get("X-Trace")
        When { get(Paths.WIDGET) } Then { statusCode(404) }
    }
}
