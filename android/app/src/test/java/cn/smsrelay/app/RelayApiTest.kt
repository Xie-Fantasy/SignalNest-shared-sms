package cn.smsrelay.app

import org.junit.Assert.*
import org.junit.Test

class RelayApiTest {
    @Test fun onlyHttpsOriginsAreAccepted() {
        val api = RelayApi()
        assertEquals("https://example.com", api.validateEndpoint("https://example.com/"))
        for (value in listOf("http://example.com", "https://user:secret@example.com",
            "https://example.com/redirect", "https://example.com?destination=elsewhere", "https://example.com#fragment")) {
            try { api.validateEndpoint(value); fail("Unsafe origin was accepted") }
            catch (_: IllegalArgumentException) { }
        }
    }
}
