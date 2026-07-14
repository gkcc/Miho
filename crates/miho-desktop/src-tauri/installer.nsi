; Pinned from tauri-apps/tauri tag tauri-v2.11.4.
; Upstream UTF-8 SHA-256: 20f4ecc730defb71f1342eaeaec4021df13be3d843abba0effe88ea5835fa079.
; Local changes add in-place upgrade semantics, a persistent installer/static/
; scheduler transaction, exact-owner uninstall, release container verification,
; running-app check ordering, and mandatory preservation of user data.
Unicode true
ManifestDPIAware true
; Add in `dpiAwareness` `PerMonitorV2` to manifest for Windows 10 1607+ (note this should not affect lower versions since they should be able to ignore this and pick up `dpiAware` `true` set by `ManifestDPIAware true`)
; Currently undocumented on NSIS's website but is in the Docs folder of source tree, see
; https://github.com/kichik/nsis/blob/5fc0b87b819a9eec006df4967d08e522ddd651c9/Docs/src/attributes.but#L286-L300
; https://github.com/tauri-apps/tauri/pull/10106
ManifestDPIAwareness PerMonitorV2

!if "{{compression}}" == "none"
  SetCompress off
!else
  ; Set the compression algorithm. We default to LZMA.
  SetCompressor /SOLID "{{compression}}"
!endif

; Keep above !include to stay ahead of any plugin command
; see https://github.com/tauri-apps/tauri/pull/15422#discussion_r3289239624
{{#if signed_plugins_path}}
!addplugindir "{{signed_plugins_path}}"
{{/if}}

!include MUI2.nsh
!include FileFunc.nsh
!include x64.nsh
!include WordFunc.nsh
!include "utils.nsh"
!include "FileAssociation.nsh"
!include "Win\COM.nsh"
!include "Win\Propkey.nsh"
!include "StrFunc.nsh"
${StrCase}
${StrLoc}

{{#if installer_hooks}}
!include "{{installer_hooks}}"
{{/if}}

!define WEBVIEW2APPGUID "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

!define MANUFACTURER "{{manufacturer}}"
!define PRODUCTNAME "{{product_name}}"
!define VERSION "{{version}}"
!define VERSIONWITHBUILD "{{version_with_build}}"
!define HOMEPAGE "{{homepage}}"
!define INSTALLMODE "{{install_mode}}"
!define LICENSE "{{license}}"
!define INSTALLERICON "{{installer_icon}}"
!define SIDEBARIMAGE "{{sidebar_image}}"
!define HEADERIMAGE "{{header_image}}"
!define UNINSTALLERICON "{{uninstaller_icon}}"
!define UNINSTALLERHEADERIMAGE "{{uninstaller_header_image}}"
!define MAINBINARYNAME "{{main_binary_name}}"
!define MAINBINARYSRCPATH "{{main_binary_path}}"
!define BUNDLEID "{{bundle_id}}"
!define COPYRIGHT "{{copyright}}"
!define OUTFILE "{{out_file}}"
!define ARCH "{{arch}}"
!define ADDITIONALPLUGINSPATH "{{additional_plugins_path}}"
!define ALLOWDOWNGRADES "{{allow_downgrades}}"
!define DISPLAYLANGUAGESELECTOR "{{display_language_selector}}"
!define INSTALLWEBVIEW2MODE "{{install_webview2_mode}}"
!define WEBVIEW2INSTALLERARGS "{{webview2_installer_args}}"
!define WEBVIEW2BOOTSTRAPPERPATH "{{webview2_bootstrapper_path}}"
!define WEBVIEW2INSTALLERPATH "{{webview2_installer_path}}"
!define MINIMUMWEBVIEW2VERSION "{{minimum_webview2_version}}"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCTNAME}"
!define MANUKEY "Software\${MANUFACTURER}"
!define MANUPRODUCTKEY "${MANUKEY}\${PRODUCTNAME}"
!define UNINSTALLERSIGNCOMMAND "{{uninstaller_sign_cmd}}"
!define ESTIMATEDSIZE "{{estimated_size}}"
!define STARTMENUFOLDER "{{start_menu_folder}}"
!define MIHO_RELEASE_VERIFY_NONCE "__MIHO_RELEASE_VERIFY_NONCE__"
; This key is a product protocol constant shared with the Rust desktop. It is
; deliberately not MANUPRODUCTKEY, whose publisher-derived path can change.
!define MIHO_AUTOMATION_OWNER_REGKEY "Software\${BUNDLEID}"
!define MIHO_AUTOMATION_OWNER_REGVALUE "AutomationOwnerInstanceIdV1"
!define MIHO_INSTALLER_COMMITTED_EXIT 10
!define MIHO_LEGACY_XML_SHA256 "b26bae8018d142c8665d7ed31080ad4218ed1611215adce860c90429d7eebf3e"
!define MIHO_LEGACY_SDDL_SHA256 "6e5ba45af9ba52d430ea6f5aa8bdfcd9d388a4ba8eabb20614d6f014948f75fb"

Var PassiveMode
Var UpdateMode
Var NoShortcutMode
Var WixMode
Var OldMainBinaryName
Var MihoVerifyStaticDir
Var MihoInstallerLease
Var MihoInstallerTransactionRoot
Var MihoInstallerStagingRoot
Var MihoInstallerHelper
Var MihoInstallerPowerShell
Var MihoInstallerFailure
Var MihoUninstallOwner
Var MihoUninstallStagingRoot
Var MihoUninstallHelper
Var MihoUninstallWrapper
Var MihoUninstallRecoveryMode
Var MihoInstalledVersionComparison

Name "${PRODUCTNAME}"
BrandingText "${COPYRIGHT}"
OutFile "${OUTFILE}"

; We don't actually use this value as default install path,
; it's just for nsis to append the product name folder in the directory selector
; https://nsis.sourceforge.io/Reference/InstallDir
!define PLACEHOLDER_INSTALL_DIR "placeholder\${PRODUCTNAME}"
InstallDir "${PLACEHOLDER_INSTALL_DIR}"

VIProductVersion "${VERSIONWITHBUILD}"
VIAddVersionKey "ProductName" "${PRODUCTNAME}"
VIAddVersionKey "FileDescription" "${PRODUCTNAME}"
VIAddVersionKey "LegalCopyright" "${COPYRIGHT}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"

# additional plugins
!addplugindir "${ADDITIONALPLUGINSPATH}"

; Uninstaller signing command
!if "${UNINSTALLERSIGNCOMMAND}" != ""
  !uninstfinalize '${UNINSTALLERSIGNCOMMAND}'
!endif

; Handle install mode, `perUser`, `perMachine` or `both`
!if "${INSTALLMODE}" == "perMachine"
  RequestExecutionLevel admin
!endif

!if "${INSTALLMODE}" == "currentUser"
  RequestExecutionLevel user
!endif

!if "${INSTALLMODE}" == "both"
  !define MULTIUSER_MUI
  !define MULTIUSER_INSTALLMODE_INSTDIR "${PRODUCTNAME}"
  !define MULTIUSER_INSTALLMODE_COMMANDLINE
  !if "${ARCH}" == "x64"
    !define MULTIUSER_USE_PROGRAMFILES64
  !else if "${ARCH}" == "arm64"
    !define MULTIUSER_USE_PROGRAMFILES64
  !endif
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_KEY "${UNINSTKEY}"
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_VALUENAME "CurrentUser"
  !define MULTIUSER_INSTALLMODEPAGE_SHOWUSERNAME
  !define MULTIUSER_INSTALLMODE_FUNCTION RestorePreviousInstallLocation
  !define MULTIUSER_EXECUTIONLEVEL Highest
  !include MultiUser.nsh
!endif

; Installer icon
!if "${INSTALLERICON}" != ""
  !define MUI_ICON "${INSTALLERICON}"
!endif

; Installer sidebar image
!if "${SIDEBARIMAGE}" != ""
  !define MUI_WELCOMEFINISHPAGE_BITMAP "${SIDEBARIMAGE}"
!endif

; Enable header images for installer and uninstaller pages when either image is configured.
!if "${HEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE
!else if "${UNINSTALLERHEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE
!endif

; Installer header image
!if "${HEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE_BITMAP "${HEADERIMAGE}"
!endif

; Uninstaller header image
!if "${UNINSTALLERHEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE_UNBITMAP "${UNINSTALLERHEADERIMAGE}"
!endif

; Uninstaller icon
!if "${UNINSTALLERICON}" != ""
  !define MUI_UNICON "${UNINSTALLERICON}"
!endif

; Define registry key to store installer language
!define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
!define MUI_LANGDLL_REGISTRY_KEY "${MANUPRODUCTKEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "Installer Language"

; Installer pages, must be ordered as they appear
; 1. Welcome Page
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_WELCOME

; 2. License Page (if defined)
!if "${LICENSE}" != ""
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !insertmacro MUI_PAGE_LICENSE "${LICENSE}"
!endif

; 3. Install mode (if it is set to `both`)
!if "${INSTALLMODE}" == "both"
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !insertmacro MULTIUSER_PAGE_INSTALLMODE
!endif

; 4. Custom page to ask user if he wants to reinstall/uninstall
;    only if a previous installation was detected
Var ReinstallPageCheck
Page custom PageReinstall PageLeaveReinstall
Function PageReinstall
  ; Uninstall previous WiX installation if exists.
  ;
  ; A WiX installer stores the installation info in registry
  ; using a UUID and so we have to loop through all keys under
  ; `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`
  ; and check if `DisplayName` and `Publisher` keys match ${PRODUCTNAME} and ${MANUFACTURER}
  ;
  ; This has a potential issue that there maybe another installation that matches
  ; our ${PRODUCTNAME} and ${MANUFACTURER} but wasn't installed by our WiX installer,
  ; however, this should be fine since the user will have to confirm the uninstallation
  ; and they can chose to abort it if doesn't make sense.
  StrCpy $0 0
  wix_loop:
    EnumRegKey $1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" $0
    StrCmp $1 "" wix_loop_done ; Exit loop if there is no more keys to loop on
    IntOp $0 $0 + 1
    ReadRegStr $R0 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "DisplayName"
    ReadRegStr $R1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "Publisher"
    StrCmp "$R0$R1" "${PRODUCTNAME}${MANUFACTURER}" 0 wix_loop
    ReadRegStr $R0 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "UninstallString"
    ${StrCase} $R1 $R0 "L"
    ${StrLoc} $R0 $R1 "msiexec" ">"
    StrCmp $R0 0 0 wix_loop_done
    StrCpy $WixMode 1
    StrCpy $R6 "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1"
    Goto compare_version
  wix_loop_done:

  ; Check if there is an existing installation, if not, abort the reinstall page
  ReadRegStr $R0 SHCTX "${UNINSTKEY}" ""
  ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"
  ${IfThen} "$R0$R1" == "" ${|} Abort ${|}

  ; Compare this installar version with the existing installation
  ; and modify the messages presented to the user accordingly
  compare_version:
  StrCpy $R4 "$(older)"
  ${If} $WixMode = 1
    ReadRegStr $R0 HKLM "$R6" "DisplayVersion"
  ${Else}
    ReadRegStr $R0 SHCTX "${UNINSTKEY}" "DisplayVersion"
  ${EndIf}
  ${IfThen} $R0 == "" ${|} StrCpy $R4 "$(unknown)" ${|}

  nsis_tauri_utils::SemverCompare "${VERSION}" $R0
  Pop $R0
  StrCpy $MihoInstalledVersionComparison $R0
  ; Reinstalling the same version
  ${If} $R0 = 0
    StrCpy $R1 "$(alreadyInstalledLong)"
    StrCpy $R2 "$(addOrReinstall)"
    StrCpy $R3 "$(uninstallApp)"
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(chooseMaintenanceOption)"
  ; Upgrading
  ${ElseIf} $R0 = 1
    StrCpy $R1 "$(olderOrUnknownVersionInstalled)"
    ; Version replacement is a rollback-capable in-place transaction. The old
    ; uninstaller must not destroy the only rollback source first.
    StrCpy $R2 "$(dontUninstall)"
    StrCpy $R3 "$(uninstallBeforeInstalling)"
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"
  ; Downgrading
  ${ElseIf} $R0 = -1
    StrCpy $R1 "$(newerVersionInstalled)"
    StrCpy $R2 "$(dontUninstall)"
    !if "${ALLOWDOWNGRADES}" == "true"
      StrCpy $R3 "$(uninstallBeforeInstalling)"
    !else
      StrCpy $R3 "$(dontUninstallDowngrade)"
    !endif
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"
  ${Else}
    Abort
  ${EndIf}

  ; Skip showing the page if passive
  ;
  ; Note that we don't call this earlier at the begining
  ; of this function because we need to populate some variables
  ; related to current installed version if detected and whether
  ; we are downgrading or not.
  ${If} $PassiveMode = 1
    Call PageLeaveReinstall
  ${Else}
    nsDialogs::Create 1018
    Pop $R4
    ${IfThen} $(^RTL) = 1 ${|} nsDialogs::SetRTL $(^RTL) ${|}

    ${NSD_CreateLabel} 0 0 100% 24u $R1
    Pop $R1

    ${NSD_CreateRadioButton} 30u 50u -30u 8u $R2
    Pop $R2
    ${NSD_OnClick} $R2 PageReinstallUpdateSelection

    ${NSD_CreateRadioButton} 30u 70u -30u 8u $R3
    Pop $R3
    ; Disable this radio button if downgrading and downgrades are disabled
    !if "${ALLOWDOWNGRADES}" == "false"
      ${IfThen} $R0 = -1 ${|} EnableWindow $R3 0 ${|}
    !endif
    ${NSD_OnClick} $R3 PageReinstallUpdateSelection
    ${If} $WixMode <> 1
    ${AndIf} $R0 <> 0
      EnableWindow $R3 0
    ${EndIf}

    ; Check the first radio button if this the first time
    ; we enter this page or if the second button wasn't
    ; selected the last time we were on this page
    ${If} $WixMode <> 1
    ${AndIf} $R0 <> 0
      SendMessage $R2 ${BM_SETCHECK} ${BST_CHECKED} 0
      SendMessage $R3 ${BM_SETCHECK} ${BST_UNCHECKED} 0
      StrCpy $ReinstallPageCheck 1
    ${ElseIf} $ReinstallPageCheck <> 2
      SendMessage $R2 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${Else}
      SendMessage $R3 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${EndIf}

    ${NSD_SetFocus} $R2
    nsDialogs::Show
  ${EndIf}
FunctionEnd
Function PageReinstallUpdateSelection
  ${NSD_GetState} $R2 $R1
  ${If} $R1 == ${BST_CHECKED}
    StrCpy $ReinstallPageCheck 1
  ${Else}
    StrCpy $ReinstallPageCheck 2
  ${EndIf}
FunctionEnd
Function PageLeaveReinstall
  ${NSD_GetState} $R2 $R1

  ; If migrating from Wix, always uninstall
  ${If} $WixMode = 1
    Goto reinst_uninstall
  ${EndIf}

  ; In update mode, always proceeds without uninstalling
  ${If} $UpdateMode = 1
    Goto reinst_done
  ${EndIf}

  ; $R0 holds whether same(0)/upgrading(1)/downgrading(-1) version
  ; $R1 holds the radio buttons state:
  ;   1 => first choice was selected
  ;   0 => second choice was selected
  ${If} $R0 = 0 ; Same version, proceed
    ${If} $R1 = 1              ; User chose to add/reinstall
      Goto reinst_done
    ${Else}                    ; User chose to uninstall
      Goto reinst_uninstall
    ${EndIf}
  ${ElseIf} $R0 = 1 ; Upgrading
    Goto reinst_done           ; Always retain the old rollback source
  ${ElseIf} $R0 = -1 ; Downgrading
    Goto reinst_done           ; Always retain the old rollback source
  ${EndIf}

  reinst_uninstall:
    HideWindow
    ClearErrors

    ${If} $WixMode = 1
      ReadRegStr $R1 HKLM "$R6" "UninstallString"
      ExecWait '$R1' $0
    ${Else}
      ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
      ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"
      ; Keep side-by-side automation generations intact when an interactive
      ; installer replaces a different app version. The old uninstaller must
      ; observe update semantics even when the new installer was double-clicked.
      ${If} $UpdateMode = 1
      ${OrIf} $R0 <> 0
        StrCpy $R1 "$R1 /UPDATE"
      ${EndIf}
      ${IfThen} $PassiveMode = 1 ${|} StrCpy $R1 "$R1 /P" ${|} ; append /P
      StrCpy $R1 "$R1 _?=$4" ; append uninstall directory
      ExecWait '$R1' $0
    ${EndIf}

    BringToFront

    ${IfThen} ${Errors} ${|} StrCpy $0 2 ${|} ; ExecWait failed, set fake exit code

    ${If} $0 <> 0
    ${OrIf} ${FileExists} "$INSTDIR\${MAINBINARYNAME}.exe"
      ; User cancelled wix uninstaller? return to select un/reinstall page
      ${If} $WixMode = 1
      ${AndIf} $0 = 1602
        Abort
      ${EndIf}

      ; User cancelled NSIS uninstaller? return to select un/reinstall page
      ${If} $0 = 1
        Abort
      ${EndIf}

      ; Other erros? show generic error message and return to select un/reinstall page
      MessageBox MB_ICONEXCLAMATION "$(unableToUninstall)"
      Abort
    ${EndIf}
  reinst_done:
FunctionEnd

; 5. Choose install directory page
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_DIRECTORY

; 6. Start menu shortcut page
Var AppStartMenuFolder
!if "${STARTMENUFOLDER}" != ""
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !define MUI_STARTMENUPAGE_DEFAULTFOLDER "${STARTMENUFOLDER}"
!else
  !define MUI_PAGE_CUSTOMFUNCTION_PRE Skip
!endif
!insertmacro MUI_PAGE_STARTMENU Application $AppStartMenuFolder

; 7. Installation page
!insertmacro MUI_PAGE_INSTFILES

; 8. Finish page
;
; Don't auto jump to finish page after installation page,
; because the installation page has useful info that can be used debug any issues with the installer.
!define MUI_FINISHPAGE_NOAUTOCLOSE
; Use show readme button in the finish page as a button create a desktop shortcut
!define MUI_FINISHPAGE_SHOWREADME
!define MUI_FINISHPAGE_SHOWREADME_TEXT "$(createDesktop)"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateOrUpdateDesktopShortcut
; Show run app after installation.
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION RunMainBinary
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_FINISH

Function RunMainBinary
  nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" ""
FunctionEnd

; Uninstaller Pages
; 1. Confirm uninstall page
; Mutable workspace, Box, config, receipts and output data are never owned by
; the installer. Do not display a generic recursive AppData deletion option.
!define MUI_PAGE_CUSTOMFUNCTION_PRE un.SkipIfPassive
!insertmacro MUI_UNPAGE_CONFIRM

; 2. Uninstalling Page
!insertmacro MUI_UNPAGE_INSTFILES

;Languages
{{#each languages}}
!insertmacro MUI_LANGUAGE "{{this}}"
{{/each}}
!insertmacro MUI_RESERVEFILE_LANGDLL
{{#each language_files}}
  !include "{{this}}"
{{/each}}

Function .onInit
  ; Page callbacks do not run for /S installs. Keep downgrade policy on a
  ; dedicated variable instead of reading a scratch register left behind by
  ; GetOptions or another macro when this is a true clean silent install.
  StrCpy $MihoInstalledVersionComparison ""
  ClearErrors
  ${GetOptions} $CMDLINE "/MIHO_VERIFY_STATIC=" $MihoVerifyStaticDir
  ${IfNot} ${Errors}
    StrCmp $MihoVerifyStaticDir "" miho_verify_static_init_failed
    ClearErrors
    FileOpen $0 "$MihoVerifyStaticDir\.miho-static-container-verification-v1" r
    IfErrors miho_verify_static_init_failed
    FileRead $0 $1
    FileClose $0
    StrCmp $1 "${MIHO_RELEASE_VERIFY_NONCE}" 0 miho_verify_static_init_failed
    Delete "$MihoVerifyStaticDir\.miho-static-container-verification-v1"
    IfErrors miho_verify_static_init_failed
    StrCpy $INSTDIR $MihoVerifyStaticDir
    StrCpy $PassiveMode 1
    StrCpy $NoShortcutMode 1
    StrCpy $UpdateMode 1
    SetSilent silent
    Return
  ${EndIf}

  ${GetOptions} $CMDLINE "/P" $PassiveMode
  ${IfNot} ${Errors}
    StrCpy $PassiveMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/NS" $NoShortcutMode
  ${IfNot} ${Errors}
    StrCpy $NoShortcutMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/UPDATE" $UpdateMode
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
  ${EndIf}

  !if "${DISPLAYLANGUAGESELECTOR}" == "true"
    !insertmacro MUI_LANGDLL_DISPLAY
  !endif

  !insertmacro SetContext

  ; Establish the NSIS-installed version relation even when every page is
  ; skipped. Interactive installs recompute the same value in PageReinstall;
  ; a missing uninstall version deliberately remains "not installed".
  ReadRegStr $R1 SHCTX "${UNINSTKEY}" "DisplayVersion"
  ${If} $R1 != ""
    nsis_tauri_utils::SemverCompare "${VERSION}" $R1
    Pop $MihoInstalledVersionComparison
  ${EndIf}

  ${If} $INSTDIR == "${PLACEHOLDER_INSTALL_DIR}"
    ; Set default install location
    !if "${INSTALLMODE}" == "perMachine"
      ${If} ${RunningX64}
        !if "${ARCH}" == "x64"
          StrCpy $INSTDIR "$PROGRAMFILES64\${PRODUCTNAME}"
        !else if "${ARCH}" == "arm64"
          StrCpy $INSTDIR "$PROGRAMFILES64\${PRODUCTNAME}"
        !else
          StrCpy $INSTDIR "$PROGRAMFILES\${PRODUCTNAME}"
        !endif
      ${Else}
        StrCpy $INSTDIR "$PROGRAMFILES\${PRODUCTNAME}"
      ${EndIf}
    !else if "${INSTALLMODE}" == "currentUser"
      StrCpy $INSTDIR "$LOCALAPPDATA\${PRODUCTNAME}"
    !endif

    Call RestorePreviousInstallLocation
  ${EndIf}


  !if "${INSTALLMODE}" == "both"
    !insertmacro MULTIUSER_INIT
  !endif
  Return

miho_verify_static_init_failed:
  SetErrorLevel 1603
  Abort "Static payload verification request is invalid."
FunctionEnd


Section EarlyChecks
  StrCmp $MihoVerifyStaticDir "" 0 miho_early_checks_done
  ; Abort silent installer if downgrades is disabled
  !if "${ALLOWDOWNGRADES}" == "false"
  ${If} ${Silent}
    ; If downgrading
    ${If} $MihoInstalledVersionComparison = -1
      System::Call 'kernel32::AttachConsole(i -1)i.r0'
      ${If} $0 <> 0
        System::Call 'kernel32::GetStdHandle(i -11)i.r0'
        System::call 'kernel32::SetConsoleTextAttribute(i r0, i 0x0004)' ; set red color
        FileWrite $0 "$(silentDowngrades)"
      ${EndIf}
      Abort
    ${EndIf}
  ${EndIf}
  !endif

miho_early_checks_done:
SectionEnd

Section WebView2
  StrCmp $MihoVerifyStaticDir "" 0 webview2_done
  ; Check if Webview2 is already installed and skip this section
  ${If} ${RunningX64}
    ReadRegStr $4 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${Else}
    ReadRegStr $4 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${EndIf}
  ${If} $4 == ""
    ReadRegStr $4 HKCU "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${EndIf}

  ${If} $4 == ""
    ; Webview2 installation
    ;
    ; Skip if updating
    ${If} $UpdateMode <> 1
      !if "${INSTALLWEBVIEW2MODE}" == "downloadBootstrapper"
        Delete "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        DetailPrint "$(webview2Downloading)"
        NSISdl::download "https://go.microsoft.com/fwlink/p/?LinkId=2124703" "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Pop $0
        ${If} $0 == "success"
          DetailPrint "$(webview2DownloadSuccess)"
        ${Else}
          DetailPrint "$(webview2DownloadError)"
          Abort "$(webview2AbortError)"
        ${EndIf}
        StrCpy $6 "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Goto install_webview2
      !endif

      !if "${INSTALLWEBVIEW2MODE}" == "embedBootstrapper"
        Delete "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        File "/oname=$TEMP\MicrosoftEdgeWebview2Setup.exe" "${WEBVIEW2BOOTSTRAPPERPATH}"
        DetailPrint "$(installingWebview2)"
        StrCpy $6 "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Goto install_webview2
      !endif

      !if "${INSTALLWEBVIEW2MODE}" == "offlineInstaller"
        Delete "$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe"
        File "/oname=$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe" "${WEBVIEW2INSTALLERPATH}"
        DetailPrint "$(installingWebview2)"
        StrCpy $6 "$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe"
        Goto install_webview2
      !endif

      Goto webview2_done

      install_webview2:
        DetailPrint "$(installingWebview2)"
        ; $6 holds the path to the webview2 installer
        ExecWait "$6 ${WEBVIEW2INSTALLERARGS} /install" $1
        ${If} $1 = 0
          DetailPrint "$(webview2InstallSuccess)"
        ${Else}
          DetailPrint "$(webview2InstallError)"
          Abort "$(webview2AbortError)"
        ${EndIf}
      webview2_done:
    ${EndIf}
  ${Else}
    !if "${MINIMUMWEBVIEW2VERSION}" != ""
      ${VersionCompare} "${MINIMUMWEBVIEW2VERSION}" "$4" $R0
      ${If} $R0 = 1
        update_webview:
          DetailPrint "$(installingWebview2)"
          ${If} ${RunningX64}
            ReadRegStr $R1 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate" "path"
          ${Else}
            ReadRegStr $R1 HKLM "SOFTWARE\Microsoft\EdgeUpdate" "path"
          ${EndIf}
          ${If} $R1 == ""
            ReadRegStr $R1 HKCU "SOFTWARE\Microsoft\EdgeUpdate" "path"
          ${EndIf}
          ${If} $R1 != ""
            ; Chromium updater docs: https://source.chromium.org/chromium/chromium/src/+/main:docs/updater/user_manual.md
            ; Modified from "HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft EdgeWebView\ModifyPath"
            ExecWait `"$R1" /install appguid=${WEBVIEW2APPGUID}&needsadmin=true` $1
            ${If} $1 = 0
              DetailPrint "$(webview2InstallSuccess)"
            ${Else}
              MessageBox MB_ICONEXCLAMATION|MB_ABORTRETRYIGNORE "$(webview2InstallError)" IDIGNORE ignore IDRETRY update_webview
              Quit
              ignore:
            ${EndIf}
          ${EndIf}
      ${EndIf}
    !endif
  ${EndIf}
SectionEnd

!macro MIHO_SET_ENV NAME VALUE
  System::Call 'kernel32::SetEnvironmentVariableW(w "${NAME}", w "${VALUE}") i.R9'
  StrCmp $R9 0 miho_environment_failed
!macroend

!macro MIHO_CLEAR_ENV NAME
  System::Call 'kernel32::SetEnvironmentVariableW(w "${NAME}", p 0) i.R9'
  StrCmp $R9 0 miho_environment_failed
!macroend

!macro MIHO_RUN_INSTALLER_HELPER MODE
  ClearErrors
  ExecWait '"$MihoInstallerPowerShell" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$MihoInstallerHelper" -Mode "${MODE}"' $0
!macroend

Function MihoAcquireInstallerLease
  StrCpy $MihoInstallerLease ""
  StrCpy $R8 "$LOCALAPPDATA\com.miho.endgame.installer-v1.lock"
  System::Call 'kernel32::CreateFileW(w R8, i 0xC0000000, i 0, p 0, i 4, i 0x00200080, p 0) p.r0'
  StrCpy $MihoInstallerLease $0
  StrCmp $MihoInstallerLease "-1" miho_installer_lease_failed

  System::Call 'kernel32::GetFileAttributesW(w R8) i.r1'
  StrCmp $1 "-1" miho_installer_lease_close_failed
  IntOp $2 $1 & 0x00000410
  StrCmp $2 0 +2
    Goto miho_installer_lease_close_failed

  ; The persistent lock file is only a kernel lease anchor.  Its contents are
  ; never evidence and are forced to zero bytes while the exclusive handle is
  ; held, so a stale or pre-created normal file cannot carry hidden state.
  System::Call 'kernel32::SetFilePointer(p r0, i 0, p 0, i 0) i.r1'
  StrCmp $1 "-1" miho_installer_lease_close_failed
  System::Call 'kernel32::SetEndOfFile(p r0) i.r1'
  StrCmp $1 0 miho_installer_lease_close_failed
  ClearErrors
  Return

miho_installer_lease_close_failed:
  System::Call 'kernel32::CloseHandle(p r0) i.r1'
miho_installer_lease_failed:
  StrCpy $MihoInstallerLease ""
  SetErrors
FunctionEnd

Function MihoReleaseInstallerLease
  StrCmp $MihoInstallerLease "" miho_installer_lease_released
  StrCpy $0 $MihoInstallerLease
  System::Call 'kernel32::CloseHandle(p r0) i.r1'
  StrCpy $MihoInstallerLease ""
miho_installer_lease_released:
FunctionEnd

Function un.MihoAcquireInstallerLease
  StrCpy $MihoInstallerLease ""
  StrCpy $R8 "$LOCALAPPDATA\com.miho.endgame.installer-v1.lock"
  System::Call 'kernel32::CreateFileW(w R8, i 0xC0000000, i 0, p 0, i 4, i 0x00200080, p 0) p.r0'
  StrCpy $MihoInstallerLease $0
  StrCmp $MihoInstallerLease "-1" un_miho_installer_lease_failed
  System::Call 'kernel32::GetFileAttributesW(w R8) i.r1'
  StrCmp $1 "-1" un_miho_installer_lease_close_failed
  IntOp $2 $1 & 0x00000410
  StrCmp $2 0 +2
    Goto un_miho_installer_lease_close_failed
  System::Call 'kernel32::SetFilePointer(p r0, i 0, p 0, i 0) i.r1'
  StrCmp $1 "-1" un_miho_installer_lease_close_failed
  System::Call 'kernel32::SetEndOfFile(p r0) i.r1'
  StrCmp $1 0 un_miho_installer_lease_close_failed
  ClearErrors
  Return

un_miho_installer_lease_close_failed:
  System::Call 'kernel32::CloseHandle(p r0) i.r1'
un_miho_installer_lease_failed:
  StrCpy $MihoInstallerLease ""
  SetErrors
FunctionEnd

Function un.MihoReleaseInstallerLease
  StrCmp $MihoInstallerLease "" un_miho_installer_lease_released
  StrCpy $0 $MihoInstallerLease
  System::Call 'kernel32::CloseHandle(p r0) i.r1'
  StrCpy $MihoInstallerLease ""
un_miho_installer_lease_released:
FunctionEnd

!macro MIHO_COPY_STATIC_PAYLOAD ROOT
  ; Copy main executable
  File "${MAINBINARYSRCPATH}"

  ; Copy resources
  {{#each resources_dirs}}
    CreateDirectory "${ROOT}\\{{this}}"
  {{/each}}
  {{#each resources}}
    File /a "/oname={{this.[1]}}" "{{no-escape @key}}"
  {{/each}}

  ; Copy external binaries
  {{#each binaries}}
    File /a "/oname={{this}}" "{{no-escape @key}}"
  {{/each}}
!macroend

Section Install
  StrCmp $MihoVerifyStaticDir "" miho_normal_install
  SetOutPath $INSTDIR
  ClearErrors
  !insertmacro MIHO_COPY_STATIC_PAYLOAD "$INSTDIR"
  IfErrors miho_verify_static_failed
  Goto miho_install_done

miho_verify_static_failed:
  SetErrorLevel 1603
  Abort "Static payload container verification extraction failed."

miho_normal_install:
  !ifmacrodef NSIS_HOOK_PREINSTALL
    !insertmacro NSIS_HOOK_PREINSTALL
  !endif

  !insertmacro CheckIfAppIsRunning "${MAINBINARYNAME}.exe" "${PRODUCTNAME}"

  ; Serialize every installer for this Windows user.  The handle is inherited
  ; by no child and is released explicitly after terminal Commit/Rollback.
  Call MihoAcquireInstallerLease
  IfErrors miho_installer_busy

  ; Extract the immutable payload away from $INSTDIR.  Begin captures durable
  ; before-images before ApplyStatic performs the first product mutation.
  InitPluginsDir
  StrCpy $MihoInstallerStagingRoot "$PLUGINSDIR\miho-installer-staging-v1"
  StrCpy $MihoInstallerHelper "$MihoInstallerStagingRoot\installer\installer_transaction_v1.ps1"
  StrCpy $MihoInstallerPowerShell "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"
  StrCpy $MihoInstallerTransactionRoot "$LOCALAPPDATA\com.miho.endgame.installer-transaction-v1"
  RMDir /r "$MihoInstallerStagingRoot"
  CreateDirectory "$MihoInstallerStagingRoot"
  SetOutPath "$MihoInstallerStagingRoot"
  ClearErrors
  !insertmacro MIHO_COPY_STATIC_PAYLOAD "$MihoInstallerStagingRoot"
  IfErrors miho_staging_failed
  IfFileExists "$MihoInstallerHelper" +2 0
    Goto miho_staging_failed

  ; The helper consumes only inherited process environment for paths/identity;
  ; no user-controlled filesystem path or owner is interpolated into a command
  ; line.  Explicitly clear optional inherited values before setting policy.
  StrCmp $AppStartMenuFolder "" 0 +2
    StrCpy $AppStartMenuFolder "${STARTMENUFOLDER}"
  StrCpy $R7 "0"
  ${If} $NoShortcutMode = 1
  ${OrIf} $UpdateMode = 1
    StrCpy $R7 "1"
  ${EndIf}
  StrCpy $R6 "0"
  ${If} $R7 <> 1
    ${If} $PassiveMode = 1
    ${OrIf} ${Silent}
      StrCpy $R6 "1"
    ${EndIf}
  ${EndIf}
  ; SetEnvironmentVariable treats an empty value as deletion, so an explicit
  ; marker carries Tauri's root-of-Programs shortcut policy to PowerShell.
  StrCpy $R4 "0"
  StrCmp $AppStartMenuFolder "" 0 +2
    StrCpy $R4 "1"
  System::Call 'kernel32::GetCurrentProcessId() i.R5'
  Delete "$LOCALAPPDATA\com.miho.endgame.installer-last-failure-v1.json"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_TRANSACTION_ROOT_V1" "$MihoInstallerTransactionRoot"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_FAILURE_RECEIPT_V1" "$LOCALAPPDATA\com.miho.endgame.installer-last-failure-v1.json"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_INSTALL_ROOT_V1" "$INSTDIR"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_STAGING_ROOT_V1" "$MihoInstallerStagingRoot"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_COORDINATOR_PID_V1" "$R5"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_PRODUCT_NAME_V1" "${PRODUCTNAME}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_MANUFACTURER_V1" "${MANUFACTURER}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_PRODUCT_VERSION_V1" "${VERSION}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_MAIN_BINARY_V1" "${MAINBINARYNAME}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_START_MENU_V1" "$AppStartMenuFolder"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_START_MENU_ROOT_V1" "$R4"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_DESKTOP_SHORTCUT_V1" "$R6"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_NO_SHORTCUTS_V1" "$R7"
  !insertmacro MIHO_CLEAR_ENV "MIHO_INSTALLER_WORKSPACE_V1"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_DEFAULT_WORKSPACE_V1" "$APPDATA\${BUNDLEID}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_DESKTOP_SETTINGS_V1" "$APPDATA\${BUNDLEID}\desktop-settings-v1.json"
  !insertmacro MIHO_CLEAR_ENV "MIHO_INSTALLER_CONFIG_V1"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_AUTOMATION_ROOT_V1" "$LOCALAPPDATA\com.miho.endgame.automation"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_LEGACY_XML_SHA256_V1" "${MIHO_LEGACY_XML_SHA256}"
  !insertmacro MIHO_SET_ENV "MIHO_INSTALLER_LEGACY_SDDL_SHA256_V1" "${MIHO_LEGACY_SDDL_SHA256}"

  ; A previous killed installer must reach a terminal state before this payload
  ; can capture a new before-image under the same lease.
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Recover"
  IfErrors miho_recover_failed
  StrCmp $0 "0" +2
    Goto miho_recover_failed

  !insertmacro MIHO_RUN_INSTALLER_HELPER "Begin"
  IfErrors miho_begin_failed
  StrCmp $0 "0" +2
    Goto miho_begin_failed

  !insertmacro MIHO_RUN_INSTALLER_HELPER "Claim"
  IfErrors miho_claim_failed
  StrCmp $0 "0" +2
    Goto miho_claim_failed

  !insertmacro MIHO_RUN_INSTALLER_HELPER "ApplyStatic"
  IfErrors miho_static_apply_failed
  StrCmp $0 "0" +2
    Goto miho_static_apply_failed

  CreateDirectory "$APPDATA\${BUNDLEID}"
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Prepare"
  IfErrors miho_prepare_failed
  StrCmp $0 "0" +2
    Goto miho_prepare_failed

  ; Create file associations
  ClearErrors
  {{#each file_associations as |association| ~}}
    {{#each association.ext as |ext| ~}}
       !insertmacro APP_ASSOCIATE "{{ext}}" "{{or association.name ext}}" "{{association-description association.description ext}}" "$INSTDIR\${MAINBINARYNAME}.exe,0" "Open with ${PRODUCTNAME}" "$INSTDIR\${MAINBINARYNAME}.exe $\"%1$\""
    {{/each}}
  {{/each}}
  IfErrors miho_association_failed

  ; Register deep links
  ClearErrors
  {{#each deep_link_protocols as |protocol| ~}}
    WriteRegStr SHCTX "Software\Classes\\{{protocol}}" "URL Protocol" ""
    WriteRegStr SHCTX "Software\Classes\\{{protocol}}" "" "URL:${BUNDLEID} protocol"
    WriteRegStr SHCTX "Software\Classes\\{{protocol}}\DefaultIcon" "" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\",0"
    WriteRegStr SHCTX "Software\Classes\\{{protocol}}\shell\open\command" "" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\" $\"%1$\""
  {{/each}}
  IfErrors miho_deep_link_failed

  ; Create uninstaller
  ClearErrors
  WriteUninstaller "$INSTDIR\uninstall.exe"
  IfErrors miho_uninstaller_failed

  ; Read the old binary identity for shortcut migration before clearing the
  ; optional missing-value error and before overwriting uninstall metadata.
  ReadRegStr $OldMainBinaryName SHCTX "${UNINSTKEY}" "MainBinaryName"
  ClearErrors

  ; Save $INSTDIR in registry for future installations
  WriteRegStr SHCTX "${MANUPRODUCTKEY}" "" $INSTDIR

  !if "${INSTALLMODE}" == "both"
    ; Save install mode to be selected by default for the next installation such as updating
    ; or when uninstalling
    WriteRegStr SHCTX "${UNINSTKEY}" $MultiUser.InstallMode 1
  !endif

  ; Save current MAINBINARYNAME for future updates
  WriteRegStr SHCTX "${UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"

  ; Registry information for add/remove programs
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayName" "${PRODUCTNAME}"
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${UNINSTKEY}" "Publisher" "${MANUFACTURER}"
  WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegDWORD SHCTX "${UNINSTKEY}" "NoModify" "1"
  WriteRegDWORD SHCTX "${UNINSTKEY}" "NoRepair" "1"

  ${GetSize} "$INSTDIR" "/M=uninstall.exe /S=0K /G=0" $0 $1 $2
  IntOp $0 $0 + ${ESTIMATEDSIZE}
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD SHCTX "${UNINSTKEY}" "EstimatedSize" "$0"

  !if "${HOMEPAGE}" != ""
    WriteRegStr SHCTX "${UNINSTKEY}" "URLInfoAbout" "${HOMEPAGE}"
    WriteRegStr SHCTX "${UNINSTKEY}" "URLUpdateInfo" "${HOMEPAGE}"
    WriteRegStr SHCTX "${UNINSTKEY}" "HelpLink" "${HOMEPAGE}"
  !endif
  IfErrors miho_registry_failed

  ; Create start menu shortcut
  ClearErrors
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    Call CreateOrUpdateStartMenuShortcut
  !insertmacro MUI_STARTMENU_WRITE_END
  IfErrors miho_start_menu_failed

  ; Create desktop shortcut for silent and passive installers
  ; because finish page will be skipped
  ClearErrors
  ${If} $PassiveMode = 1
  ${OrIf} ${Silent}
    Call CreateOrUpdateDesktopShortcut
  ${EndIf}
  IfErrors miho_desktop_shortcut_failed

  ; Verify every static hash, dynamic file/shortcut and registry before the
  ; scheduled-task switch becomes the final fallible product mutation.
  !insertmacro MIHO_RUN_INSTALLER_HELPER "VerifyDynamic"
  IfErrors miho_dynamic_verify_failed
  StrCmp $0 "0" +2
    Goto miho_dynamic_verify_failed

  !insertmacro MIHO_RUN_INSTALLER_HELPER "Commit"
  IfErrors miho_commit_failed
  StrCmp $0 "0" miho_install_committed miho_commit_failed

miho_install_committed:
  ; Commit is terminal. Finalize is cleanup-only and must never trigger a
  ; rollback; a later installer will recover any cleanup-pending journal.
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Finalize"
  Call MihoReleaseInstallerLease

  ; Auto close this page for passive mode
  ${If} $PassiveMode = 1
    SetAutoClose true
  ${EndIf}
  Goto miho_install_done

miho_installer_busy:
  SetErrorLevel 1603
  Abort "Another Miho Endgame installer or uninstaller is active for this user."

miho_staging_failed:
  StrCpy $MihoInstallerFailure "immutable payload staging"
  Goto miho_install_failed_without_transaction

miho_environment_failed:
  StrCpy $MihoInstallerFailure "transaction environment setup"
  Goto miho_install_failed_without_transaction

miho_recover_failed:
  StrCpy $MihoInstallerFailure "recovery of a prior interrupted installer"
  Goto miho_install_unresolved

miho_begin_failed:
  StrCpy $MihoInstallerFailure "durable installer Begin"
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Recover"
  IfErrors miho_install_unresolved
  StrCmp $0 "0" miho_install_rolled_back miho_install_unresolved

miho_claim_failed:
  StrCpy $MihoInstallerFailure "automation owner Claim"
  Goto miho_install_rollback
miho_static_apply_failed:
  StrCpy $MihoInstallerFailure "static payload ApplyStatic"
  Goto miho_install_rollback
miho_prepare_failed:
  StrCpy $MihoInstallerFailure "candidate run and Prepare"
  Goto miho_install_rollback
miho_association_failed:
  StrCpy $MihoInstallerFailure "file association registration"
  Goto miho_install_rollback
miho_deep_link_failed:
  StrCpy $MihoInstallerFailure "deep-link registration"
  Goto miho_install_rollback
miho_uninstaller_failed:
  StrCpy $MihoInstallerFailure "uninstaller creation"
  Goto miho_install_rollback
miho_registry_failed:
  StrCpy $MihoInstallerFailure "product registry registration"
  Goto miho_install_rollback
miho_start_menu_failed:
  StrCpy $MihoInstallerFailure "start-menu shortcut registration"
  Goto miho_install_rollback
miho_desktop_shortcut_failed:
  StrCpy $MihoInstallerFailure "desktop shortcut registration"
  Goto miho_install_rollback
miho_dynamic_verify_failed:
  StrCpy $MihoInstallerFailure "dynamic-state verification"
  Goto miho_install_rollback
miho_commit_failed:
  StrCpy $MihoInstallerFailure "terminal automation Commit"

miho_install_rollback:
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Rollback"
  IfErrors miho_install_unresolved
  StrCmp $0 "${MIHO_INSTALLER_COMMITTED_EXIT}" miho_install_committed
  StrCmp $0 "0" miho_install_rolled_back miho_install_unresolved

miho_install_rolled_back:
  ; A normal rollback remains a failed installation. Finalize is best effort.
  !insertmacro MIHO_RUN_INSTALLER_HELPER "Finalize"
  Call MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Miho Endgame setup failed during $MihoInstallerFailure. The previous installer-owned files, registry, shortcuts and scheduled task were rolled back. Details were saved to $LOCALAPPDATA\com.miho.endgame.installer-last-failure-v1.json." /SD IDOK
  Abort "Miho Endgame setup failed and was rolled back."

miho_install_failed_without_transaction:
  Call MihoReleaseInstallerLease
  SetErrorLevel 1603
  Abort "Miho Endgame setup failed before a product transaction began ($MihoInstallerFailure)."

miho_install_unresolved:
  Call MihoReleaseInstallerLease
  SetErrorLevel 1603
  MessageBox MB_ICONSTOP|MB_OK "Miho Endgame setup could not prove a terminal state during $MihoInstallerFailure. Product mutation is stopped; the durable installer journal is retained for exact recovery by the next setup run." /SD IDOK
  Abort "Miho Endgame installer recovery is pending."

miho_install_done:
SectionEnd

Function .onInstSuccess
  StrCmp $MihoVerifyStaticDir "" +2 0
    Return
  ; Check for `/R` flag only in silent and passive installers because
  ; GUI installer has a toggle for the user to (re)start the app
  ${If} $PassiveMode = 1
  ${OrIf} ${Silent}
    ${GetOptions} $CMDLINE "/R" $R0
    ${IfNot} ${Errors}
      ${GetOptions} $CMDLINE "/ARGS" $R0
      nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" "$R0"
    ${EndIf}
  ${EndIf}
FunctionEnd

Function un.onInit
  !insertmacro SetContext

  !if "${INSTALLMODE}" == "both"
    !insertmacro MULTIUSER_UNINIT
  !endif

  !insertmacro MUI_UNGETLANGUAGE

  ${GetOptions} $CMDLINE "/P" $PassiveMode
  ${IfNot} ${Errors}
    StrCpy $PassiveMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/UPDATE" $UpdateMode
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
  ${EndIf}
FunctionEnd

Section Uninstall

  ; A cancelled running-app prompt must not remove the scheduled task first.
  !insertmacro CheckIfAppIsRunning "${MAINBINARYNAME}.exe" "${PRODUCTNAME}"

  ; Execute uninstall policy from bytes embedded in uninstall.exe, never from
  ; an installed script whose hash is about to be verified.  Resource files
  ; are intentionally duplicated into the uninstaller data block so recovery
  ; remains available even when an installed helper drifted.
  InitPluginsDir
  StrCpy $MihoUninstallStagingRoot "$PLUGINSDIR\miho-uninstall-policy-v1"
  StrCpy $MihoUninstallHelper "$MihoUninstallStagingRoot\installer\installer_transaction_v1.ps1"
  StrCpy $MihoUninstallWrapper "$MihoUninstallStagingRoot\installer\uninstall_daily_update_task.ps1"
  RMDir /r "$MihoUninstallStagingRoot"
  CreateDirectory "$MihoUninstallStagingRoot"
  SetOutPath "$MihoUninstallStagingRoot"
  ClearErrors
  {{#each resources_dirs}}
    CreateDirectory "$MihoUninstallStagingRoot\\{{this}}"
  {{/each}}
  {{#each resources}}
    File /a "/oname={{this.[1]}}" "{{no-escape @key}}"
  {{/each}}
  IfErrors miho_uninstall_policy_staging_failed
  IfFileExists "$MihoUninstallHelper" +2 0
    Goto miho_uninstall_policy_staging_failed
  IfFileExists "$MihoUninstallWrapper" miho_uninstall_policy_staged 0

miho_uninstall_policy_staging_failed:
  SetErrorLevel 1603
  Abort "The exact embedded uninstall policy could not be extracted. No product state was removed."

miho_uninstall_policy_staged:

  ; Workspace, Box, config, receipts and outputs are user data. This product
  ; has no recursive AppData deletion UI or uninstall branch.

  !ifmacrodef NSIS_HOOK_PREUNINSTALL
    !insertmacro NSIS_HOOK_PREUNINSTALL
  !endif

  ; Delete the app directory and its content from disk
  ; Copy main executable
  Delete "$INSTDIR\${MAINBINARYNAME}.exe"

  ; Delete resources
  {{#each resources}}
    Delete "$INSTDIR\\{{this.[1]}}"
  {{/each}}

  ; Delete external binaries
  {{#each binaries}}
    Delete "$INSTDIR\\{{this}}"
  {{/each}}

  ; Delete app associations
  {{#each file_associations as |association| ~}}
    {{#each association.ext as |ext| ~}}
      !insertmacro APP_UNASSOCIATE "{{ext}}" "{{or association.name ext}}"
    {{/each}}
  {{/each}}

  ; Delete deep links
  {{#each deep_link_protocols as |protocol| ~}}
    ReadRegStr $R7 SHCTX "Software\Classes\\{{protocol}}\shell\open\command" ""
    ${If} $R7 == "$\"$INSTDIR\${MAINBINARYNAME}.exe$\" $\"%1$\""
      DeleteRegKey SHCTX "Software\Classes\\{{protocol}}"
    ${EndIf}
  {{/each}}


  ; Delete uninstaller
  Delete "$INSTDIR\uninstall.exe"

  {{#each resources_ancestors}}
  RMDir /REBOOTOK "$INSTDIR\\{{this}}"
  {{/each}}
  RMDir "$INSTDIR"

  ; Remove shortcuts if not updating
  ${If} $UpdateMode <> 1
    !insertmacro DeleteAppUserModelId

    ; Remove start menu shortcut
    !insertmacro MUI_STARTMENU_GETFOLDER Application $AppStartMenuFolder
    !insertmacro IsShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      Delete "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      RMDir "$SMPROGRAMS\$AppStartMenuFolder"
    ${EndIf}
    !insertmacro IsShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk"
      Delete "$SMPROGRAMS\${PRODUCTNAME}.lnk"
    ${EndIf}

    ; Remove desktop shortcuts
    !insertmacro IsShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$DESKTOP\${PRODUCTNAME}.lnk"
      Delete "$DESKTOP\${PRODUCTNAME}.lnk"
    ${EndIf}
  ${EndIf}

  ; Remove registry information for add/remove programs
  !if "${INSTALLMODE}" == "both"
    DeleteRegKey SHCTX "${UNINSTKEY}"
  !else if "${INSTALLMODE}" == "perMachine"
    DeleteRegKey HKLM "${UNINSTKEY}"
  !else
    DeleteRegKey HKCU "${UNINSTKEY}"
  !endif

  ; Removes the Autostart entry for ${PRODUCTNAME} from the HKCU Run key if it exists.
  ; This ensures the program does not launch automatically after uninstallation if it exists.
  ; If it doesn't exist, it does nothing.
  ; We do this when not updating (to preserve the registry value on updates)
  ${If} $UpdateMode <> 1
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCTNAME}"
  ${EndIf}

  ; Install-location and installer-language registry values are product
  ; metadata, not user data. Remove them even though Miho deliberately keeps
  ; workspace/config/output AppData on uninstall.
  DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
  DeleteRegKey /ifempty SHCTX "${MANUKEY}"
  DeleteRegValue HKCU "${MANUPRODUCTKEY}" "Installer Language"
  DeleteRegKey /ifempty HKCU "${MANUPRODUCTKEY}"
  DeleteRegKey /ifempty HKCU "${MANUKEY}"

  !ifmacrodef NSIS_HOOK_POSTUNINSTALL
    !insertmacro NSIS_HOOK_POSTUNINSTALL
  !endif

  ; Auto close if passive mode or updating
  ${If} $PassiveMode = 1
  ${OrIf} $UpdateMode = 1
    SetAutoClose true
  ${EndIf}
SectionEnd

Function RestorePreviousInstallLocation
  ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
  StrCmp $4 "" +2 0
    StrCpy $INSTDIR $4
FunctionEnd

Function Skip
  Abort
FunctionEnd

Function SkipIfPassive
  ${IfThen} $PassiveMode = 1  ${|} Abort ${|}
FunctionEnd
Function un.SkipIfPassive
  ${IfThen} $PassiveMode = 1  ${|} Abort ${|}
FunctionEnd

Function CreateOrUpdateStartMenuShortcut
  ; We used to use product name as MAINBINARYNAME
  ; migrate old shortcuts to target the new MAINBINARYNAME
  StrCpy $R0 0

  !insertmacro IsShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    StrCpy $R0 1
  ${EndIf}

  !insertmacro IsShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    StrCpy $R0 1
  ${EndIf}

  ${If} $R0 = 1
    Return
  ${EndIf}

  ; Skip creating shortcut if in update mode or no shortcut mode
  ; but always create if migrating from wix
  ${If} $WixMode = 0
    ${If} $UpdateMode = 1
    ${OrIf} $NoShortcutMode = 1
      Return
    ${EndIf}
  ${EndIf}

  ; CreateShortcut derives WorkingDirectory from OutPath. The immutable
  ; staging directory is deleted after setup, so reset it to the install root.
  SetOutPath "$INSTDIR"
  !if "${STARTMENUFOLDER}" != ""
    CreateDirectory "$SMPROGRAMS\$AppStartMenuFolder"
    CreateShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    !insertmacro SetLnkAppUserModelId "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
  !else
    CreateShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    !insertmacro SetLnkAppUserModelId "$SMPROGRAMS\${PRODUCTNAME}.lnk"
  !endif
FunctionEnd

Function CreateOrUpdateDesktopShortcut
  ; We used to use product name as MAINBINARYNAME
  ; migrate old shortcuts to target the new MAINBINARYNAME
  !insertmacro IsShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Return
  ${EndIf}

  ; Skip creating shortcut if in update mode or no shortcut mode
  ; but always create if migrating from wix
  ${If} $WixMode = 0
    ${If} $UpdateMode = 1
    ${OrIf} $NoShortcutMode = 1
      Return
    ${EndIf}
  ${EndIf}

  ; Keep the shortcut's WorkingDirectory stable after $PLUGINSDIR is removed.
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  !insertmacro SetLnkAppUserModelId "$DESKTOP\${PRODUCTNAME}.lnk"
FunctionEnd
