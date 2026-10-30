package com.example.widgets;

public class PartsGetTest {
    @Test
    public void getPart_notFound() {
        given().when().get(Paths.PART_FMT, "t", "p").then().statusCode(404);
    }
}
