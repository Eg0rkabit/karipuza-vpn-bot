package io.nekohasekai.sfa.compose

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SupportAgent
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.lifecycleScope
import io.nekohasekai.sfa.BuildConfig
import io.nekohasekai.sfa.R
import io.nekohasekai.sfa.bg.BoxService
import io.nekohasekai.sfa.bg.ServiceConnection
import io.nekohasekai.sfa.constant.Alert
import io.nekohasekai.sfa.constant.ServiceMode
import io.nekohasekai.sfa.constant.Status
import io.nekohasekai.sfa.database.Settings
import io.nekohasekai.sfa.karipaza.AccountInfo
import io.nekohasekai.sfa.karipaza.ApiClient
import io.nekohasekai.sfa.karipaza.ApiException
import io.nekohasekai.sfa.karipaza.LoginChallenge
import io.nekohasekai.sfa.karipaza.LoginPollResult
import io.nekohasekai.sfa.karipaza.PlanInfo
import io.nekohasekai.sfa.karipaza.ProfileInstaller
import io.nekohasekai.sfa.karipaza.SecureTokenStore
import io.nekohasekai.sfa.karipaza.SubscriptionInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity :
    AppCompatActivity(),
    ServiceConnection.Callback {
    private val connection by lazy { ServiceConnection(this, this) }
    private val tokenStore by lazy { SecureTokenStore(this) }
    private val apiClient by lazy { ApiClient(BuildConfig.API_BASE_URL) }

    private var sessionToken by mutableStateOf<String?>(null)
    private var account by mutableStateOf<AccountInfo?>(null)
    private var serviceStatus by mutableStateOf(Status.Stopped)
    private var loading by mutableStateOf(false)
    private var loginChallenge by mutableStateOf<LoginChallenge?>(null)
    private var configReady by mutableStateOf(false)
    private var configUpdatedAt by mutableLongStateOf(0L)
    private var errorMessage by mutableStateOf<String?>(null)
    private var selectedTab by mutableIntStateOf(0)
    private var loginJob: Job? = null
    private var connectAfterNotificationPermission = false

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {
            if (connectAfterNotificationPermission) {
                connectAfterNotificationPermission = false
                prepareVpn()
            }
        }

    private val vpnPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                startVpnService()
            } else {
                errorMessage = "Без разрешения Android не сможет включить VPN."
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        connection.reconnect()
        sessionToken = tokenStore.readToken()
        configReady = Settings.selectedProfile > 0

        setContent {
            KaripazaTheme {
                KaripazaApp(
                    token = sessionToken,
                    account = account,
                    serviceStatus = serviceStatus,
                    loading = loading,
                    waitingForTelegram = loginChallenge != null,
                    configReady = configReady,
                    configUpdatedAt = configUpdatedAt,
                    errorMessage = errorMessage,
                    selectedTab = selectedTab,
                    onTabSelected = { selectedTab = it },
                    onLogin = ::startTelegramLogin,
                    onCancelLogin = ::cancelTelegramLogin,
                    onConnect = ::toggleVpn,
                    onRefresh = { refreshAccount(updateConfig = true) },
                    onDismissError = { errorMessage = null },
                    onLogout = ::logout,
                )
            }
        }

        if (sessionToken != null) {
            refreshAccount(updateConfig = true)
        }
    }

    private fun startTelegramLogin() {
        loginJob?.cancel()
        errorMessage = null
        loading = true
        loginJob =
            lifecycleScope.launch {
                try {
                    val deviceName =
                        "${Build.MANUFACTURER} ${Build.MODEL}"
                            .trim()
                            .replaceFirstChar { it.uppercase() }
                    val challenge =
                        apiClient.startLogin(
                            tokenStore.deviceId(),
                            deviceName,
                        )
                    loginChallenge = challenge
                    loading = false
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(challenge.botUrl)))
                    pollTelegramLogin(challenge)
                } catch (error: Exception) {
                    loading = false
                    loginChallenge = null
                    showError(error)
                }
            }
    }

    private suspend fun pollTelegramLogin(challenge: LoginChallenge) {
        var temporaryFailures = 0
        while (System.currentTimeMillis() / 1000 < challenge.expiresAt) {
            delay(challenge.pollAfterMs)
            try {
                when (val result = apiClient.completeLogin(challenge)) {
                    LoginPollResult.Pending -> temporaryFailures = 0
                    LoginPollResult.Expired -> {
                        loginChallenge = null
                        errorMessage = "Запрос устарел. Нажмите «Войти через Telegram» ещё раз."
                        return
                    }
                    is LoginPollResult.Authorized -> {
                        tokenStore.writeToken(result.token)
                        sessionToken = result.token
                        loginChallenge = null
                        selectedTab = 0
                        refreshAccount(updateConfig = true)
                        return
                    }
                }
            } catch (error: Exception) {
                temporaryFailures += 1
                if (error is ApiException && error.statusCode in 400..499) {
                    loginChallenge = null
                    showError(error)
                    return
                }
                if (temporaryFailures >= 5) {
                    loginChallenge = null
                    errorMessage =
                        "Не удалось завершить вход. Проверьте интернет и попробуйте ещё раз."
                    return
                }
            }
        }
        loginChallenge = null
        errorMessage = "Запрос устарел. Нажмите «Войти через Telegram» ещё раз."
    }

    private fun cancelTelegramLogin() {
        loginJob?.cancel()
        loginJob = null
        loginChallenge = null
        loading = false
    }

    private fun refreshAccount(
        updateConfig: Boolean,
        connectWhenReady: Boolean = false,
    ) {
        val token = sessionToken ?: return
        loading = true
        errorMessage = null
        lifecycleScope.launch {
            try {
                val freshAccount = apiClient.getAccount(token)
                account = freshAccount
                val subscription = freshAccount.subscription
                if (updateConfig && subscription?.isActive == true) {
                    val config = apiClient.getConfig(token)
                    ProfileInstaller.install(this@MainActivity, config)
                    configReady = true
                    configUpdatedAt = System.currentTimeMillis()
                    connection.reconnect()
                } else if (subscription?.isActive != true) {
                    configReady = false
                }
                if (
                    connectWhenReady &&
                    subscription?.isActive == true &&
                    configReady
                ) {
                    requestVpnStart()
                }
            } catch (error: Exception) {
                if (error is ApiException && error.statusCode == 401) {
                    clearLocalSession()
                }
                showError(error)
            } finally {
                loading = false
            }
        }
    }

    private fun toggleVpn() {
        if (serviceStatus == Status.Started || serviceStatus == Status.Starting) {
            BoxService.stop()
            return
        }
        if (account?.subscription?.isActive != true) {
            errorMessage = "Для подключения нужна активная подписка."
            selectedTab = 1
            return
        }
        if (!configReady) {
            refreshAccount(updateConfig = true, connectWhenReady = true)
            return
        }
        requestVpnStart()
    }

    private fun requestVpnStart() {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            connectAfterNotificationPermission = true
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        prepareVpn()
    }

    private fun prepareVpn() {
        Settings.serviceMode = ServiceMode.VPN
        connection.reconnect()
        val intent = VpnService.prepare(this)
        if (intent != null) {
            vpnPermissionLauncher.launch(intent)
        } else {
            startVpnService()
        }
    }

    private fun startVpnService() {
        Settings.serviceMode = ServiceMode.VPN
        Settings.startedByUser = true
        BoxService.start()
    }

    private fun logout() {
        val token = sessionToken
        BoxService.stop()
        clearLocalSession()
        if (token != null) {
            lifecycleScope.launch(Dispatchers.IO) {
                runCatching { apiClient.logout(token) }
            }
        }
    }

    private fun clearLocalSession() {
        loginJob?.cancel()
        tokenStore.clear()
        sessionToken = null
        account = null
        loginChallenge = null
        selectedTab = 0
    }

    private fun showError(error: Exception) {
        errorMessage =
            when (error) {
                is ApiException -> error.message
                else -> "Не удалось связаться с сервисом. Проверьте интернет и попробуйте ещё раз."
            }
    }

    override fun onServiceStatusChanged(status: Status) {
        runOnUiThread {
            serviceStatus = status
        }
    }

    override fun onServiceAlert(type: Alert, message: String?) {
        runOnUiThread {
            errorMessage =
                when (type) {
                    Alert.RequestVPNPermission -> "Android не выдал разрешение на VPN."
                    Alert.EmptyConfiguration -> "VPN-конфигурация пуста. Обновите подписку."
                    else -> message ?: "Не удалось запустить VPN."
                }
        }
    }

    override fun onDestroy() {
        loginJob?.cancel()
        connection.disconnect()
        super.onDestroy()
    }
}

private val KaripazaColors: ColorScheme =
    lightColorScheme(
        primary = Color(0xFF087F83),
        onPrimary = Color.White,
        primaryContainer = Color(0xFFD5F0F0),
        onPrimaryContainer = Color(0xFF073F42),
        secondary = Color(0xFF18794E),
        onSecondary = Color.White,
        secondaryContainer = Color(0xFFD9F2E4),
        onSecondaryContainer = Color(0xFF0C3F2A),
        background = Color(0xFFF1F5FA),
        onBackground = Color(0xFF17202B),
        surface = Color(0xFFF9FBFD),
        onSurface = Color(0xFF17202B),
        surfaceVariant = Color(0xFFE5EBF2),
        onSurfaceVariant = Color(0xFF526171),
        outline = Color(0xFFB8C4D0),
        error = Color(0xFFB3261E),
    )

private val KaripazaTypography =
    Typography(
        headlineSmall =
        Typography().headlineSmall.copy(
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.sp,
        ),
        titleLarge =
        Typography().titleLarge.copy(
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.sp,
        ),
        titleMedium =
        Typography().titleMedium.copy(
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.sp,
        ),
        bodyLarge = Typography().bodyLarge.copy(letterSpacing = 0.sp),
        bodyMedium = Typography().bodyMedium.copy(letterSpacing = 0.sp),
        labelLarge =
        Typography().labelLarge.copy(
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.sp,
        ),
    )

@Composable
private fun KaripazaTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            window.statusBarColor = Color.Transparent.toArgb()
            window.navigationBarColor = KaripazaColors.background.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = true
                isAppearanceLightNavigationBars = true
            }
        }
    }
    MaterialTheme(
        colorScheme = KaripazaColors,
        typography = KaripazaTypography,
        content = content,
    )
}

@Composable
private fun KaripazaApp(
    token: String?,
    account: AccountInfo?,
    serviceStatus: Status,
    loading: Boolean,
    waitingForTelegram: Boolean,
    configReady: Boolean,
    configUpdatedAt: Long,
    errorMessage: String?,
    selectedTab: Int,
    onTabSelected: (Int) -> Unit,
    onLogin: () -> Unit,
    onCancelLogin: () -> Unit,
    onConnect: () -> Unit,
    onRefresh: () -> Unit,
    onDismissError: () -> Unit,
    onLogout: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        Image(
            painter = painterResource(R.drawable.karipaza_background),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier =
            Modifier
                .fillMaxSize()
                .background(Color(0xC7F4F7FB)),
        )

        if (token == null) {
            LoginScreen(
                loading = loading,
                waitingForTelegram = waitingForTelegram,
                errorMessage = errorMessage,
                onLogin = onLogin,
                onCancelLogin = onCancelLogin,
                onDismissError = onDismissError,
            )
        } else {
            MainScreen(
                account = account,
                serviceStatus = serviceStatus,
                loading = loading,
                configReady = configReady,
                configUpdatedAt = configUpdatedAt,
                errorMessage = errorMessage,
                selectedTab = selectedTab,
                onTabSelected = onTabSelected,
                onConnect = onConnect,
                onRefresh = onRefresh,
                onDismissError = onDismissError,
                onLogout = onLogout,
            )
        }
    }
}

@Composable
private fun LoginScreen(
    loading: Boolean,
    waitingForTelegram: Boolean,
    errorMessage: String?,
    onLogin: () -> Unit,
    onCancelLogin: () -> Unit,
    onDismissError: () -> Unit,
) {
    Box(
        contentAlignment = Alignment.Center,
        modifier =
        Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Image(
                painter = painterResource(R.drawable.karipaza_logo),
                contentDescription = "Karipaza Froxy",
                contentScale = ContentScale.Crop,
                modifier =
                Modifier
                    .size(112.dp)
                    .clip(RoundedCornerShape(8.dp)),
            )
            Spacer(Modifier.height(20.dp))
            Text("Karipaza Froxy", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(8.dp))
            Text(
                "Личный VPN в одном приложении",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(28.dp))

            if (waitingForTelegram) {
                CircularProgressIndicator(modifier = Modifier.size(32.dp))
                Spacer(Modifier.height(16.dp))
                Text(
                    "Подтвердите вход в Telegram",
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(10.dp))
                TextButton(onClick = onCancelLogin) {
                    Text("Отменить")
                }
            } else {
                Button(
                    onClick = onLogin,
                    enabled = !loading,
                    shape = RoundedCornerShape(8.dp),
                    contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp),
                ) {
                    if (loading) {
                        CircularProgressIndicator(
                            color = MaterialTheme.colorScheme.onPrimary,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(20.dp),
                        )
                    } else {
                        Icon(Icons.Default.Person, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Войти через Telegram")
                    }
                }
            }
            ErrorBanner(errorMessage, onDismissError)
        }
    }
}

@Composable
private fun MainScreen(
    account: AccountInfo?,
    serviceStatus: Status,
    loading: Boolean,
    configReady: Boolean,
    configUpdatedAt: Long,
    errorMessage: String?,
    selectedTab: Int,
    onTabSelected: (Int) -> Unit,
    onConnect: () -> Unit,
    onRefresh: () -> Unit,
    onDismissError: () -> Unit,
    onLogout: () -> Unit,
) {
    val tabs =
        listOf(
            TabItem("Главная", Icons.Default.Home),
            TabItem("Подписка", Icons.Default.VpnKey),
            TabItem("Профиль", Icons.Default.Person),
        )
    Scaffold(
        containerColor = Color.Transparent,
        contentWindowInsets = WindowInsets.safeDrawing,
        topBar = {
            AppHeader(account)
        },
        bottomBar = {
            Column {
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.55f))
                NavigationBar(containerColor = Color(0xF5F8FAFD)) {
                    tabs.forEachIndexed { index, tab ->
                        NavigationBarItem(
                            selected = selectedTab == index,
                            onClick = { onTabSelected(index) },
                            icon = { Icon(tab.icon, contentDescription = tab.title) },
                            label = { Text(tab.title) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        Column(
            modifier =
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            ErrorBanner(errorMessage, onDismissError)
            AnimatedContent(
                targetState = selectedTab,
                label = "main-tabs",
                modifier = Modifier.fillMaxWidth(),
            ) { tab ->
                Column(modifier = Modifier.fillMaxWidth()) {
                    when (tab) {
                        1 ->
                            SubscriptionScreen(
                                account = account,
                                configReady = configReady,
                                configUpdatedAt = configUpdatedAt,
                                loading = loading,
                                onRefresh = onRefresh,
                            )
                        2 -> ProfileScreen(account, onLogout)
                        else ->
                            HomeScreen(
                                account = account,
                                serviceStatus = serviceStatus,
                                loading = loading,
                                configReady = configReady,
                                onConnect = onConnect,
                                onRefresh = onRefresh,
                                onOpenSubscription = { onTabSelected(1) },
                            )
                    }
                }
            }
        }
    }
}

@Composable
private fun AppHeader(account: AccountInfo?) {
    Surface(color = Color(0xEAF8FAFC)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier =
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 10.dp),
        ) {
            Image(
                painter = painterResource(R.drawable.karipaza_logo),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier =
                Modifier
                    .size(46.dp)
                    .clip(RoundedCornerShape(8.dp)),
            )
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("Karipaza Froxy", style = MaterialTheme.typography.titleLarge)
                Text(
                    account?.firstName?.let { "Привет, $it" } ?: "Защищённое подключение",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun HomeScreen(
    account: AccountInfo?,
    serviceStatus: Status,
    loading: Boolean,
    configReady: Boolean,
    onConnect: () -> Unit,
    onRefresh: () -> Unit,
    onOpenSubscription: () -> Unit,
) {
    val subscription = account?.subscription
    val connected = serviceStatus == Status.Started
    val transitioning = serviceStatus == Status.Starting || serviceStatus == Status.Stopping
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xEAF9FBFD)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(20.dp),
        ) {
            Icon(
                imageVector = if (connected) Icons.Default.CheckCircle else Icons.Outlined.Shield,
                contentDescription = null,
                tint =
                if (connected) {
                    MaterialTheme.colorScheme.secondary
                } else {
                    MaterialTheme.colorScheme.primary
                },
                modifier = Modifier.size(32.dp),
            )
            Spacer(Modifier.height(10.dp))
            Text(
                when {
                    connected -> "VPN подключён"
                    transitioning -> "Меняем состояние"
                    subscription?.isActive == true -> "Готово к подключению"
                    else -> "Нужна активная подписка"
                },
                style = MaterialTheme.typography.titleLarge,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                when {
                    connected -> "Интернет проходит через Karipaza Froxy."
                    subscription?.isActive == true && configReady ->
                        "Конфигурация загружена. Можно включать VPN."
                    subscription?.isActive == true -> "Обновите конфигурацию подписки."
                    else -> "Откройте вкладку «Подписка», чтобы проверить доступ."
                },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(22.dp))
            FilledIconButton(
                onClick = onConnect,
                enabled = !loading && !transitioning,
                shape = CircleShape,
                colors =
                IconButtonDefaults.filledIconButtonColors(
                    containerColor =
                    if (connected) {
                        MaterialTheme.colorScheme.secondary
                    } else {
                        MaterialTheme.colorScheme.primary
                    },
                ),
                modifier = Modifier.size(88.dp),
            ) {
                if (loading || transitioning) {
                    CircularProgressIndicator(
                        color = Color.White,
                        strokeWidth = 3.dp,
                        modifier = Modifier.size(32.dp),
                    )
                } else {
                    Icon(
                        Icons.Default.PowerSettingsNew,
                        contentDescription = if (connected) "Отключить" else "Подключить",
                        modifier = Modifier.size(38.dp),
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            Text(
                when {
                    loading -> "Обновляем"
                    connected -> "Отключить"
                    else -> "Подключить"
                },
            )
        }
    }
    Spacer(Modifier.height(12.dp))

    if (subscription != null) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            StatCard(
                title = "Осталось",
                value = "${subscription.daysLeft} дн.",
                modifier = Modifier.weight(1f),
            )
            StatCard(
                title = "Использовано",
                value = formatTraffic(subscription.trafficUsed),
                modifier = Modifier.weight(1f),
            )
        }
    }
    Spacer(Modifier.height(12.dp))
    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        OutlinedButton(
            onClick = onRefresh,
            enabled = !loading,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.weight(1f),
        ) {
            Icon(Icons.Default.Refresh, contentDescription = null)
            Spacer(Modifier.width(7.dp))
            Text("Обновить")
        }
        Button(
            onClick = onOpenSubscription,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.weight(1f),
        ) {
            Icon(Icons.Default.VpnKey, contentDescription = null)
            Spacer(Modifier.width(7.dp))
            Text("Подписка")
        }
    }
}

@Composable
private fun StatCard(
    title: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    OutlinedCard(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.outlinedCardColors(containerColor = Color(0xDCF9FBFD)),
        modifier = modifier,
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(
                title,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(4.dp))
            Text(value, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun SubscriptionScreen(
    account: AccountInfo?,
    configReady: Boolean,
    configUpdatedAt: Long,
    loading: Boolean,
    onRefresh: () -> Unit,
) {
    Text("Подписка", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(12.dp))
    val subscription = account?.subscription
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xEAF9FBFD)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.VpnKey,
                    contentDescription = null,
                    tint =
                    if (subscription?.isActive == true) {
                        MaterialTheme.colorScheme.secondary
                    } else {
                        MaterialTheme.colorScheme.error
                    },
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    when {
                        subscription == null -> "Подписки пока нет"
                        subscription.isActive -> "Доступ активен"
                        else -> "Доступ приостановлен"
                    },
                    style = MaterialTheme.typography.titleLarge,
                )
            }
            if (subscription != null) {
                Spacer(Modifier.height(14.dp))
                DetailRow("Действует до", formatDate(subscription.expireAt))
                DetailRow("Осталось", "${subscription.daysLeft} дней")
                DetailRow("Трафик", trafficDescription(subscription))
                DetailRow(
                    "Конфигурация",
                    if (configReady) "загружена" else "нужно обновить",
                )
                if (configUpdatedAt > 0) {
                    DetailRow("Обновлена", formatDateTime(configUpdatedAt))
                }
            }
            Spacer(Modifier.height(14.dp))
            Button(
                onClick = onRefresh,
                enabled = !loading,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.Refresh, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Обновить подписку")
            }
        }
    }
    Spacer(Modifier.height(20.dp))
    Text("Тарифы", style = MaterialTheme.typography.titleLarge)
    Spacer(Modifier.height(10.dp))
    if (account?.plans.isNullOrEmpty()) {
        Text(
            "Тарифы загружаются…",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    } else {
        account?.plans?.forEach { plan ->
            PlanCard(plan)
            Spacer(Modifier.height(9.dp))
        }
    }
    Text(
        "Оплата через Platega появится после завершения подключения.",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodyMedium,
    )
}

@Composable
private fun PlanCard(plan: PlanInfo) {
    OutlinedCard(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.outlinedCardColors(containerColor = Color(0xDCF9FBFD)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(14.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(plan.title, style = MaterialTheme.typography.titleMedium)
                    if (plan.badge.isNotBlank()) {
                        Spacer(Modifier.width(8.dp))
                        Surface(
                            color = MaterialTheme.colorScheme.primaryContainer,
                            shape = RoundedCornerShape(6.dp),
                        ) {
                            Text(
                                plan.badge,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
                            )
                        }
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "${plan.priceRub} ₽",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            OutlinedButton(
                onClick = {},
                enabled = false,
                shape = RoundedCornerShape(8.dp),
            ) {
                Text("Скоро")
            }
        }
    }
}

@Composable
private fun ProfileScreen(
    account: AccountInfo?,
    onLogout: () -> Unit,
) {
    val context = LocalContext.current
    Text("Профиль", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(12.dp))
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xEAF9FBFD)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(
                account?.firstName ?: "Пользователь Telegram",
                style = MaterialTheme.typography.titleLarge,
            )
            Spacer(Modifier.height(10.dp))
            DetailRow(
                "Telegram",
                account?.username?.let { "@$it" } ?: "ID ${account?.telegramId ?: ""}",
            )
            DetailRow("Устройство", account?.deviceName ?: "Android")
        }
    }
    Spacer(Modifier.height(12.dp))
    OutlinedButton(
        onClick = {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.BOT_URL)))
        },
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Icon(Icons.Default.SupportAgent, contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text("Открыть поддержку")
    }
    Spacer(Modifier.height(8.dp))
    OutlinedButton(
        onClick = onLogout,
        shape = RoundedCornerShape(8.dp),
        colors =
        ButtonDefaults.outlinedButtonColors(
            contentColor = MaterialTheme.colorScheme.error,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Icon(Icons.Default.Logout, contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text("Выйти из приложения")
    }
}

@Composable
private fun DetailRow(
    title: String,
    value: String,
) {
    Row(
        horizontalArrangement = Arrangement.SpaceBetween,
        modifier =
        Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp),
    ) {
        Text(
            title,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(
            value,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1.25f),
        )
    }
}

@Composable
private fun ErrorBanner(
    message: String?,
    onDismiss: () -> Unit,
) {
    AnimatedVisibility(
        visible = !message.isNullOrBlank(),
        enter = fadeIn(),
        exit = fadeOut(),
    ) {
        if (!message.isNullOrBlank()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.error.copy(alpha = 0.09f))
                    .border(
                        1.dp,
                        MaterialTheme.colorScheme.error.copy(alpha = 0.35f),
                        RoundedCornerShape(8.dp),
                    ).padding(start = 14.dp, top = 10.dp, bottom = 10.dp),
            ) {
                Text(
                    message,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "Закрыть")
                }
            }
        }
    }
}

private data class TabItem(
    val title: String,
    val icon: ImageVector,
)

private fun formatTraffic(bytes: Long): String = when {
    bytes >= 1024L * 1024 * 1024 ->
        String.format(Locale.US, "%.1f ГБ", bytes / (1024.0 * 1024 * 1024))
    bytes >= 1024L * 1024 ->
        String.format(Locale.US, "%.0f МБ", bytes / (1024.0 * 1024))
    bytes >= 1024L -> String.format(Locale.US, "%.0f КБ", bytes / 1024.0)
    else -> "$bytes Б"
}

private fun trafficDescription(subscription: SubscriptionInfo): String = if (subscription.trafficLimit <= 0) {
    "${formatTraffic(subscription.trafficUsed)} / безлимит"
} else {
    "${formatTraffic(subscription.trafficUsed)} / ${formatTraffic(subscription.trafficLimit)}"
}

private fun formatDate(timestampSeconds: Long): String {
    if (timestampSeconds <= 0) return "не указано"
    return SimpleDateFormat("dd.MM.yyyy", Locale("ru"))
        .format(Date(timestampSeconds * 1000))
}

private fun formatDateTime(timestampMillis: Long): String = SimpleDateFormat("dd.MM, HH:mm", Locale("ru")).format(Date(timestampMillis))
