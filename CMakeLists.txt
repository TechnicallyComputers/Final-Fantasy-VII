cmake_minimum_required(VERSION 3.20)
project(Final_Fantasy_7 LANGUAGES C CXX)
include(CTest)

set(PSXRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/psxrecomp" CACHE PATH
    "Path to psxrecomp")

# --- Opt-in product surfaces (OFF by default in the framework) -------------
# Scaffold prompts / flags fill these. Without recomp-ui, PSX_RECOMP_UI is OFF.
# Setup-host CI requires WIZARD_CMAKE_BLOCK / ENABLE_SETUP_WIZARD (FORCE_SETUP_HOST
# alone does not open first-run / Generate & rebuild).
# recomp-ui submodule present (PSX_RECOMP_UI defaults ON).
# Full netplay UI — enable after adding recomp-ui + testing:
# if(EXISTS "${PSXRECOMP_ROOT}/lib/recomp-net/CMakeLists.txt")
#     set(PSX_NETPLAY ON CACHE BOOL "…" FORCE)
# endif()
set(PSX_SETUP_WIZARD ON CACHE BOOL
    "Advertise first-run setup wizard + Generate & rebuild in recomp-ui" FORCE)
include("${PSXRECOMP_ROOT}/runtime/runtime.cmake")

psxrecomp_add_game_runtime(psx-runtime
    # Compile precision propagation into the primary binary. The renderer mod
    # decides whether it runs; disabling the mod retains the original math.
    PGXP
    # ENABLE_NETPLAY_IF_PRESENT
    # NETPLAY_LOBBY_URL "ws://netplay.retcomm.net:8765"
    ENABLE_SETUP_WIZARD
    WINDOW_TITLE "Final Fantasy 7"
    DEFAULT_GAME_CONFIG_PATH "game.toml"
    MAX_PLAYERS 1
    LAUNCHER_BOXART "${CMAKE_CURRENT_SOURCE_DIR}/launcher_assets/img/boxart.tga"
    APP_ICON "${CMAKE_CURRENT_SOURCE_DIR}/assets/psxrecomp.ico"
    # The framework stages this alongside its own mods/builtin/packages into
    # <exe-dir>/mods/bundled; the title must not copy it itself. Must sit
    # BEFORE GEN_FULL_GLOB/CODEGEN_SETUP_SOURCES: psxrecomp_add_game_runtime
    # does not know this keyword, so after a multi-value keyword it would be
    # swallowed into that list instead of forwarded.
    PRELOADED_MODS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/mods/preloaded"
    GEN_MARKER "generated/SCUS_941.63_dispatch.c"
    GEN_FULL_GLOB "generated/SCUS_941.63_full_*.c"
    CODEGEN_SETUP_SOURCES
        "${CMAKE_CURRENT_SOURCE_DIR}/codegen_setup.c"
        # Trusted implementations selected independently by the mod catalog.
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_mods.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_lzs.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_loading.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_renderer.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_save.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_access.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_game.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_resident.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_menu.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_battle.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_projection.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_game_save.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_rewards.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_results.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_field.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_field_assets.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/ff7_party_field_loader.c"
)
target_compile_definitions(psx-runtime PRIVATE FF7_PARTY_WITH_RUNTIME=1)
if(TARGET psx-runtime-pgxp)
    target_compile_definitions(psx-runtime-pgxp PRIVATE FF7_PARTY_WITH_RUNTIME=1)
endif()

if(BUILD_TESTING)
    add_executable(ff7-party-tests tests/test_ff7_party.c src/ff7_party.c)
    target_include_directories(ff7-party-tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    add_test(NAME ff7_party COMMAND ff7-party-tests)

    add_executable(ff7-party-access-tests tests/test_ff7_party_access.c src/ff7_party.c)
    target_include_directories(ff7-party-access-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_access_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_access COMMAND ff7-party-access-tests)

    add_executable(ff7-party-game-tests tests/test_ff7_party_game.c src/ff7_party.c)
    target_include_directories(ff7-party-game-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_game_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    target_link_libraries(ff7-party-game-tests PRIVATE ZLIB::ZLIB)
    add_test(NAME ff7_party_game COMMAND ff7-party-game-tests)

    add_executable(ff7-party-menu-tests tests/test_ff7_party_menu.c)
    target_include_directories(ff7-party-menu-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_menu_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_menu COMMAND ff7-party-menu-tests)

    add_executable(ff7-party-battle-tests tests/test_ff7_party_battle.c)
    target_include_directories(ff7-party-battle-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_battle_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_battle COMMAND ff7-party-battle-tests)

    add_executable(ff7-party-rewards-tests tests/test_ff7_party_rewards.c)
    target_include_directories(ff7-party-rewards-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_game_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_rewards COMMAND ff7-party-rewards-tests)

    add_executable(ff7-party-results-tests tests/test_ff7_party_results.c)
    target_include_directories(ff7-party-results-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_game_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_results COMMAND ff7-party-results-tests)

    add_executable(ff7-party-field-assets-tests tests/test_ff7_party_field_assets.c src/ff7_party_field_assets.c)
    target_include_directories(ff7-party-field-assets-tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    add_test(NAME ff7_party_field_assets COMMAND ff7-party-field-assets-tests)

    add_executable(ff7-party-field-loader-tests tests/test_ff7_party_field_loader.c
        src/ff7_party_field_assets.c src/ff7_party_field.c)
    target_include_directories(ff7-party-field-loader-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_field_loader_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_field_loader COMMAND ff7-party-field-loader-tests)

    add_executable(ff7-party-field-tests tests/test_ff7_party_field.c src/ff7_party_resident.c)
    target_include_directories(ff7-party-field-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_game_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_field COMMAND ff7-party-field-tests)

    add_executable(ff7-party-game-save-tests tests/test_ff7_party_game_save.c
        src/ff7_party.c src/ff7_party_projection.c)
    target_include_directories(ff7-party-game-save-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_game_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src" "${PSXRECOMP_ROOT}/runtime/include")
    add_test(NAME ff7_party_game_save COMMAND ff7-party-game-save-tests)

    add_executable(ff7-party-save-tests tests/test_ff7_party_save.c
        src/ff7_party.c src/ff7_party_save.c)
    target_include_directories(ff7-party-save-tests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/ff7_party_save_stubs"
        "${CMAKE_CURRENT_SOURCE_DIR}/src")
    add_test(NAME ff7_party_save COMMAND ff7-party-save-tests)

    add_executable(ff7-party-save-integration-tests
        tests/test_ff7_party_save_integration.c src/ff7_party.c
        src/ff7_party_save.c "${PSXRECOMP_ROOT}/runtime/src/memcard.c")
    target_include_directories(ff7-party-save-integration-tests PRIVATE
        "${PSXRECOMP_ROOT}/runtime/include" "${CMAKE_CURRENT_SOURCE_DIR}/src")
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/ff7_party_save_scratch")
    add_test(NAME ff7_party_save_integration
        COMMAND ff7-party-save-integration-tests
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/ff7_party_save_scratch")
endif()

# Stage runtime configs next to the exe for direct build/ launches. Only copy
# files that exist — never fail POST_BUILD when game_options.toml is absent.
foreach(_PSX_RUNTIME_CONFIG game.toml game_options.toml)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_PSX_RUNTIME_CONFIG}")
        add_custom_command(TARGET psx-runtime POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_CURRENT_SOURCE_DIR}/${_PSX_RUNTIME_CONFIG}"
                "$<TARGET_FILE_DIR:psx-runtime>/${_PSX_RUNTIME_CONFIG}"
            COMMENT "Staging ${_PSX_RUNTIME_CONFIG}"
            VERBATIM)
    endif()
endforeach()
