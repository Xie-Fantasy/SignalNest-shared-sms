package cn.smsrelay.app

object RelayRules {
    fun keywords(value: String) = value.split('\n', ',', '，').map { it.trim() }.filter { it.isNotEmpty() }.distinct()
    fun matches(body: String, rules: String) = keywords(rules).any { body.contains(it, ignoreCase = true) }
    fun redact(body: String) = body.replace(Regex("[0-9A-Za-z]{4,}"), "******")
    fun configKey(c: RelayConfig, vault: Vault) = vault.digest("${c.endpoint}|${c.token}|${c.recipient}|${c.boundId}|${c.simSignature}")
}
