package cn.smsrelay.app

import org.junit.Assert.*
import org.junit.Test

class SimResolverTest {
    private val lines = listOf(SimLine(10, 0, "private", "a"), SimLine(20, 1, "shared", "b"))
    @Test fun missingMetadataOnDualSimIsBlocked() {
        assertNull(SimResolver.resolve(lines, SimEvidence(emptyList(), emptyList())).id)
    }
    @Test fun subscriptionAndSlotMustAgree() {
        assertNull(SimResolver.resolve(lines, SimEvidence(listOf(20), listOf(0))).id)
        assertEquals(20, SimResolver.resolve(lines, SimEvidence(listOf(20), listOf(1))).id)
    }
    @Test fun privateCardIsNeverReportedAsShared() {
        assertEquals(10, SimResolver.resolve(lines, SimEvidence(listOf(10), listOf(0))).id)
    }
    @Test fun unknownOrConflictingAliasesAreBlocked() {
        assertNull(SimResolver.resolve(lines, SimEvidence(listOf(99), emptyList())).id)
        assertNull(SimResolver.resolve(lines, SimEvidence(listOf(20, 10), emptyList())).id)
        assertNull(SimResolver.resolve(lines, SimEvidence(listOf(20), listOf(1), true)).id)
    }
    @Test fun singleCardIsAllowedOnlyWhenMetadataDoesNotConflict() {
        assertEquals(20, SimResolver.resolve(lines.takeLast(1), SimEvidence(emptyList(), emptyList())).id)
        assertNull(SimResolver.resolve(lines.takeLast(1), SimEvidence(listOf(10), emptyList())).id)
    }
    @Test fun ambiguousActiveMappingIsBlocked() {
        assertNull(SimResolver.resolve(listOf(lines[0], lines[1].copy(slot=0)), SimEvidence(listOf(20), emptyList())).id)
    }
    @Test fun keywordRulesRequireActualMatch() {
        assertTrue(RelayRules.matches("您的验证码 000000", "验证码"))
        assertTrue(RelayRules.matches("Verification Code 000000", "验证码,verification code"))
        assertFalse(RelayRules.matches("订单号 000000", "验证码"))
        assertFalse(RelayRules.matches("验证码", "  , \n"))
    }
    @Test fun dualSimNeedsBothRealLineTests() {
        val bound = RelayConfig(boundId = 20, simSignature = SimResolver.signature(lines))
        assertFalse(SimResolver.ready(bound, lines))
        assertFalse(SimResolver.ready(bound.copy(testedIds = setOf(20)), lines))
        assertTrue(SimResolver.ready(bound.copy(testedIds = setOf(10, 20)), lines))
    }
    @Test fun changedSubscriptionMapInvalidatesPriorTests() {
        val bound = RelayConfig(boundId = 20, simSignature = SimResolver.signature(lines), testedIds = setOf(10, 20))
        assertFalse(SimResolver.ready(bound, lines.takeLast(1)))
        assertFalse(SimResolver.ready(bound, lines.map { it.copy(slot = 1 - it.slot) }))
        assertFalse(SimResolver.ready(bound.copy(simSignature = "older-system"), lines))
    }
}
