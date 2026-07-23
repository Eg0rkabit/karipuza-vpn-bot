package io.nekohasekai.sfa.karipaza

data class LoginChallenge(
    val requestId: String,
    val secret: String,
    val botUrl: String,
    val expiresAt: Long,
    val pollAfterMs: Long,
)

sealed interface LoginPollResult {
    data object Pending : LoginPollResult

    data object Expired : LoginPollResult

    data class Authorized(
        val token: String,
        val expiresAt: Long,
    ) : LoginPollResult
}

data class SubscriptionInfo(
    val status: String,
    val expireAt: Long,
    val daysLeft: Int,
    val trafficUsed: Long,
    val trafficLimit: Long,
    val isActive: Boolean,
)

data class PlanInfo(
    val code: String,
    val title: String,
    val days: Int,
    val priceRub: Int,
    val badge: String,
)

data class AccountInfo(
    val telegramId: Long,
    val username: String?,
    val firstName: String?,
    val deviceName: String,
    val subscription: SubscriptionInfo?,
    val plans: List<PlanInfo>,
    val syncError: Boolean,
)
