package io.nekohasekai.sfa.karipaza

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ApiException(
    val statusCode: Int,
    override val message: String,
) : RuntimeException(message)

class ApiClient(private val baseUrl: String) {
    suspend fun startLogin(
        deviceId: String,
        deviceName: String,
    ): LoginChallenge = withContext(Dispatchers.IO) {
        val body =
            JSONObject()
                .put("deviceId", deviceId)
                .put("deviceName", deviceName)
                .put("platform", "ANDROID")
        val response = request("/api/mobile/auth/start", "POST", body = body)
        val json = JSONObject(response.body)
        LoginChallenge(
            requestId = json.getString("requestId"),
            secret = json.getString("secret"),
            botUrl = json.getString("botUrl"),
            expiresAt = json.getLong("expiresAt"),
            pollAfterMs = json.optLong("pollAfterMs", 1500L).coerceAtLeast(1000L),
        )
    }

    suspend fun completeLogin(challenge: LoginChallenge): LoginPollResult = withContext(Dispatchers.IO) {
        val body =
            JSONObject()
                .put("requestId", challenge.requestId)
                .put("secret", challenge.secret)
        val response =
            request(
                "/api/mobile/auth/complete",
                "POST",
                body = body,
                acceptedStatuses = setOf(200, 202, 410),
            )
        when (response.statusCode) {
            202 -> LoginPollResult.Pending
            410 -> LoginPollResult.Expired
            else -> {
                val json = JSONObject(response.body)
                LoginPollResult.Authorized(
                    token = json.getString("token"),
                    expiresAt = json.getLong("expiresAt"),
                )
            }
        }
    }

    suspend fun getAccount(token: String): AccountInfo = withContext(Dispatchers.IO) {
        val response = request("/api/mobile/me", "GET", token = token)
        val json = JSONObject(response.body)
        val user = json.getJSONObject("user")
        val device = json.getJSONObject("device")
        val subscriptionJson = json.optJSONObject("subscription")
        val subscription =
            subscriptionJson?.let {
                SubscriptionInfo(
                    status = it.optString("status", "UNKNOWN"),
                    expireAt = it.optLong("expireAt", 0L),
                    daysLeft = it.optInt("daysLeft", 0),
                    trafficUsed = it.optLong("trafficUsed", 0L),
                    trafficLimit = it.optLong("trafficLimit", 0L),
                    isActive = it.optBoolean("isActive", false),
                )
            }
        val plansJson = json.optJSONArray("plans")
        val plans = buildList {
            if (plansJson != null) {
                for (index in 0 until plansJson.length()) {
                    val plan = plansJson.getJSONObject(index)
                    add(
                        PlanInfo(
                            code = plan.getString("code"),
                            title = plan.getString("title"),
                            days = plan.getInt("days"),
                            priceRub = plan.getInt("priceRub"),
                            badge = plan.optString("badge"),
                        ),
                    )
                }
            }
        }
        AccountInfo(
            telegramId = user.getLong("tgId"),
            username = user.optNullableString("username"),
            firstName = user.optNullableString("firstName"),
            deviceName = device.optString("name", "Android"),
            subscription = subscription,
            plans = plans,
            syncError = json.optBoolean("syncError", false),
        )
    }

    suspend fun getConfig(token: String): String = withContext(Dispatchers.IO) {
        val response = request("/api/mobile/config", "GET", token = token)
        val config = JSONObject(response.body)
        val outbounds = config.optJSONArray("outbounds")
        if (outbounds == null || outbounds.length() == 0) {
            throw ApiException(502, "Сервер вернул пустую VPN-конфигурацию.")
        }
        response.body
    }

    suspend fun logout(token: String) {
        withContext(Dispatchers.IO) {
            request("/api/mobile/logout", "POST", token = token, body = JSONObject())
        }
    }

    private fun request(
        path: String,
        method: String,
        token: String? = null,
        body: JSONObject? = null,
        acceptedStatuses: Set<Int> = setOf(200, 201),
    ): HttpResult {
        val connection =
            (URL("${baseUrl.trimEnd('/')}$path").openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 12_000
                readTimeout = 25_000
                useCaches = false
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", "Karipaza-Froxy-Android/0.1")
                if (token != null) {
                    setRequestProperty("Authorization", "Bearer $token")
                }
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
            }
        try {
            if (body != null) {
                connection.outputStream.use { output ->
                    output.write(body.toString().toByteArray(Charsets.UTF_8))
                }
            }
            val statusCode = connection.responseCode
            val stream =
                if (statusCode in 200..299) {
                    connection.inputStream
                } else {
                    connection.errorStream
                }
            val responseBody =
                stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (statusCode !in acceptedStatuses) {
                val serverMessage =
                    runCatching {
                        JSONObject(responseBody).optString("error")
                    }.getOrNull()
                throw ApiException(
                    statusCode,
                    friendlyError(statusCode, serverMessage),
                )
            }
            return HttpResult(statusCode, responseBody)
        } finally {
            connection.disconnect()
        }
    }

    private fun friendlyError(statusCode: Int, serverMessage: String?): String = when (statusCode) {
        401 -> "Сессия закончилась. Войдите через Telegram ещё раз."
        403 -> "Подписка сейчас не активна."
        404 -> "Активная подписка не найдена."
        410 -> "Запрос на вход устарел."
        in 500..599 -> "Сервис временно недоступен. Попробуйте чуть позже."
        else -> serverMessage?.takeIf { it.isNotBlank() } ?: "Не удалось выполнить запрос."
    }

    private data class HttpResult(
        val statusCode: Int,
        val body: String,
    )
}

private fun JSONObject.optNullableString(name: String): String? = if (isNull(name)) {
    null
} else {
    optString(name).takeIf { it.isNotBlank() }
}
