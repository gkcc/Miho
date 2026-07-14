; Miho release automation hooks.
;
; The updater executable launched by Task Scheduler is copied to an
; installer-owned side-by-side generation outside $INSTDIR. No installed task
; points at the application copy that an upgrade overwrites in place.

!macro NSIS_HOOK_PREUNINSTALL
  ; Box/config/output data is outside installer ownership. Keep the upstream
  ; recursive app-data branch disabled even if its checkbox was selected.
  StrCpy $DeleteAppDataCheckboxState 0

  ; The pinned template invokes an old uninstaller with /UPDATE during every
  ; upgrade. Preserve its task/generation until the new candidate has passed
  ; update run plus config-bound health and committed the task transaction.
  StrCmp $UpdateMode "1" miho_preuninstall_done

  Call un.MihoAcquireInstallerLease
  IfErrors miho_preuninstall_busy
  StrCpy $MihoUninstallRecoveryMode "0"

  System::Call 'kernel32::SetEnvironmentVariableW(w "MIHO_INSTALLER_TRANSACTION_ROOT_V1", w "$LOCALAPPDATA\com.miho.endgame.installer-transaction-v1") i.r9'
  StrCmp $R9 0 miho_preuninstall_environment_failed
  System::Call 'kernel32::SetEnvironmentVariableW(w "MIHO_INSTALLER_INSTALL_ROOT_V1", w "$INSTDIR") i.r9'
  StrCmp $R9 0 miho_preuninstall_environment_failed

  ReadRegStr $MihoUninstallOwner HKCU "${MIHO_AUTOMATION_OWNER_REGKEY}" "${MIHO_AUTOMATION_OWNER_REGVALUE}"
  StrCmp $MihoUninstallOwner "" miho_preuninstall_owner_missing
  System::Call 'kernel32::SetEnvironmentVariableW(w "MIHO_INSTALLER_EXPECTED_OWNER_V1", w "$MihoUninstallOwner") i.r9'
  StrCmp $R9 0 miho_preuninstall_environment_failed

  ; Fail closed before removing the task: every manifest-owned static byte must
  ; still match its release size/hash and remain below a non-reparse root.
  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoUninstallHelper" -Mode "VerifyUninstallStatic"' $0
  IfErrors miho_preuninstall_static_verify_failed
  IntCmp $0 0 miho_preuninstall_static_verified miho_preuninstall_static_verify_failed miho_preuninstall_static_verify_failed

miho_preuninstall_static_verified:
  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoUninstallWrapper" -ExpectedOwnerKind "installed" -ExpectedOwnerInstanceId "$MihoUninstallOwner" -AutomationRoot "$LOCALAPPDATA\com.miho.endgame.automation"' $0
  IfErrors miho_preuninstall_launch_failed
  IntCmp $0 0 miho_preuninstall_automation_removed miho_preuninstall_command_failed miho_preuninstall_command_failed

miho_preuninstall_automation_removed:
  ; Recheck immediately after exact automation release, then remove only the
  ; manifest-owned static bytes. User data and unknown $INSTDIR files remain.
  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoUninstallHelper" -Mode "RemoveUninstallStatic"' $0
  IfErrors miho_preuninstall_static_remove_failed
  IntCmp $0 0 miho_preuninstall_done miho_preuninstall_static_remove_failed miho_preuninstall_static_remove_failed

miho_preuninstall_busy:
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Another Miho Endgame installer or uninstaller is active for this user." /SD IDOK
  Abort "Another installer or uninstaller is active."

miho_preuninstall_owner_missing:
  ; The only accepted missing-owner state is a prior uninstall that removed the
  ; owner and all static bytes, then died before journal cleanup.  The embedded
  ; helper proves that terminal receipt before this retry continues.
  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoUninstallHelper" -Mode "FinalizeUninstallStatic"' $0
  IfErrors miho_preuninstall_owner_missing_unproven
  IntCmp $0 0 miho_preuninstall_owner_missing_recovered miho_preuninstall_owner_missing_unproven miho_preuninstall_owner_missing_unproven

miho_preuninstall_owner_missing_recovered:
  StrCpy $MihoUninstallRecoveryMode "1"
  Goto miho_preuninstall_done

miho_preuninstall_owner_missing_unproven:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "The installed automation owner identity is missing without an exact terminal uninstall receipt. No additional product or user state was removed." /SD IDOK
  Abort "Installed automation owner identity is missing."

miho_preuninstall_environment_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  Abort "Static uninstall environment could not be established."

miho_preuninstall_static_verify_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Installer-owned application bytes are missing, drifted or unsafe. The scheduled task, application files and user data were preserved." /SD IDOK
  Abort "Installer-owned static payload verification failed."

miho_preuninstall_launch_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Windows could not launch the owned scheduled-task removal helper. No application files or user data were removed." /SD IDOK
  Abort "Owned scheduled-task removal helper could not be launched."

miho_preuninstall_command_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Owned scheduled-task removal failed validation. No application files or user data were removed (code $0)." /SD IDOK
  Abort "Owned scheduled-task removal failed validation."

miho_preuninstall_static_remove_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "The exact scheduled-task owner was released, but installer-owned static removal did not finish. The owner registry value and all user data were preserved; rerun uninstall to continue safely (code $0)." /SD IDOK
  Abort "Installer-owned static payload removal is incomplete."

miho_preuninstall_done:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  StrCmp $UpdateMode "1" miho_postuninstall_done
  StrCmp $MihoUninstallRecoveryMode "1" miho_postuninstall_release_only
  ReadRegStr $R8 HKCU "${MIHO_AUTOMATION_OWNER_REGKEY}" "${MIHO_AUTOMATION_OWNER_REGVALUE}"
  StrCmp $R8 $MihoUninstallOwner 0 miho_postuninstall_owner_drifted
  ClearErrors
  DeleteRegValue HKCU "${MIHO_AUTOMATION_OWNER_REGKEY}" "${MIHO_AUTOMATION_OWNER_REGVALUE}"
  IfErrors miho_postuninstall_owner_delete_failed
  ReadRegStr $R8 HKCU "${MIHO_AUTOMATION_OWNER_REGKEY}" "${MIHO_AUTOMATION_OWNER_REGVALUE}"
  StrCmp $R8 "" 0 miho_postuninstall_owner_delete_failed
  DeleteRegKey /ifempty HKCU "${MIHO_AUTOMATION_OWNER_REGKEY}"
  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoUninstallHelper" -Mode "FinalizeUninstallStatic"' $0
  IfErrors miho_postuninstall_finalize_failed
  IntCmp $0 0 miho_postuninstall_release_only miho_postuninstall_finalize_failed miho_postuninstall_finalize_failed

miho_postuninstall_release_only:
  Call un.MihoReleaseInstallerLease
  Goto miho_postuninstall_done

miho_postuninstall_owner_drifted:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Application files were removed, but the installed automation owner identity drifted. The foreign registry value was preserved." /SD IDOK
  Abort "Installed automation owner identity drifted during uninstall."

miho_postuninstall_owner_delete_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Application files were removed, but the exact installed automation owner registry value could not be cleared." /SD IDOK
  Abort "Installed automation owner identity cleanup failed."

miho_postuninstall_finalize_failed:
  Call un.MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Application and automation ownership were removed, but terminal uninstall journal cleanup is pending. A later installer or uninstaller will verify and finish cleanup." /SD IDOK
  Abort "Terminal uninstall journal cleanup is pending."

miho_postuninstall_done:
!macroend
