# Fetch the released SDK, or use an existing checkout for development.
option(SLIC3R_OPENAXIS "Enable OpenAxis camera navigation" OFF)
set(OPENAXIS_SOURCE_DIR "" CACHE PATH "OpenAxis checkout (local development override)")
if(SLIC3R_OPENAXIS)
    if(EMSCRIPTEN OR NOT SLIC3R_GUI)
        message(FATAL_ERROR "OpenAxis integration currently requires the native GUI")
    endif()
    if(CMAKE_VERSION VERSION_LESS 3.24)
        message(FATAL_ERROR "OpenAxis requires CMake 3.24 or newer")
    endif()
    # Use OrcaSlicer's bundled JSON types throughout the process. Fetching a
    # second copy would duplicate its target and mix incompatible JSON ABIs.
    if(TARGET nlohmann_json AND NOT TARGET nlohmann_json::nlohmann_json)
        target_include_directories(nlohmann_json INTERFACE "${CMAKE_CURRENT_LIST_DIR}/../deps_src")
        add_library(nlohmann_json::nlohmann_json ALIAS nlohmann_json)
    endif()
    set(OPENAXIS_BUILD_TESTS OFF CACHE BOOL "Build OpenAxis tests separately")
    set(OPENAXIS_BUILD_DEMO OFF CACHE BOOL "Build OpenAxis reference app separately")
    if(OPENAXIS_SOURCE_DIR)
        if(NOT EXISTS "${OPENAXIS_SOURCE_DIR}/cpp/CMakeLists.txt")
            message(FATAL_ERROR "OPENAXIS_SOURCE_DIR must point to an OpenAxis checkout containing cpp/CMakeLists.txt")
        endif()
        add_subdirectory("${OPENAXIS_SOURCE_DIR}/cpp" "${PROJECT_BINARY_DIR}/openaxis")
    else()
        include(FetchContent)
        FetchContent_Declare(openaxis
            GIT_REPOSITORY https://github.com/rotatrix/openaxis.git
            GIT_TAG cpp/v1.0.0-rc.1
            SOURCE_SUBDIR cpp
        )
        FetchContent_MakeAvailable(openaxis)
    endif()
endif()
