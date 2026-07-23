package io.nekohasekai.sfa.karipaza

import android.content.Context
import io.nekohasekai.libbox.Libbox
import io.nekohasekai.sfa.constant.ServiceMode
import io.nekohasekai.sfa.database.Profile
import io.nekohasekai.sfa.database.ProfileManager
import io.nekohasekai.sfa.database.Settings
import io.nekohasekai.sfa.database.TypedProfile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Date

object ProfileInstaller {
    private const val PROFILE_NAME = "Karipaza Froxy"
    private const val PREFERENCES = "karipaza_profile"
    private const val PROFILE_ID = "profile_id"

    suspend fun install(
        context: Context,
        config: String,
    ): Profile = withContext(Dispatchers.IO) {
        Libbox.checkConfig(config)
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        val savedProfileId = preferences.getLong(PROFILE_ID, -1L)
        val existing =
            if (savedProfileId > 0) {
                ProfileManager.get(savedProfileId)
            } else {
                null
            }

        val profile =
            if (existing != null) {
                existing
            } else {
                val fileId = ProfileManager.nextFileID()
                val configDirectory = File(context.filesDir, "configs").also { it.mkdirs() }
                Profile(
                    name = PROFILE_NAME,
                    userOrder = ProfileManager.nextOrder(),
                    typed =
                    TypedProfile().apply {
                        type = TypedProfile.Type.Local
                        path = File(configDirectory, "$fileId.json").path
                    },
                )
            }

        val configFile = File(profile.typed.path)
        configFile.parentFile?.mkdirs()
        val temporary = File(configFile.parentFile, "${configFile.name}.new")
        temporary.writeText(config)
        if (!temporary.renameTo(configFile)) {
            temporary.copyTo(configFile, overwrite = true)
            temporary.delete()
        }

        profile.name = PROFILE_NAME
        profile.typed.type = TypedProfile.Type.Local
        profile.typed.remoteURL = ""
        profile.typed.autoUpdate = false
        profile.typed.lastUpdated = Date()
        if (existing == null) {
            ProfileManager.create(profile, andSelect = true)
            preferences.edit().putLong(PROFILE_ID, profile.id).apply()
        } else {
            ProfileManager.update(profile)
            Settings.selectedProfile = profile.id
        }
        Settings.serviceMode = ServiceMode.VPN
        profile
    }
}
