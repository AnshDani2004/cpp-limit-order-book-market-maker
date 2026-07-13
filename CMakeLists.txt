cmake_minimum_required(VERSION 3.20)

project(cpp_limit_order_book_market_maker VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(LOB_ENABLE_WARNINGS "Enable compiler warnings" ON)

add_library(lob_core
    src/csv_io.cpp
    src/flat_order_book.cpp
    src/market_maker_simulation.cpp
    src/matching_engine.cpp
    src/order_book.cpp
    src/price_level.cpp
    src/simulation.cpp
)

target_include_directories(lob_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(lob_core PUBLIC cxx_std_20)

if(LOB_ENABLE_WARNINGS)
    if(MSVC)
        target_compile_options(lob_core PRIVATE /W4 /permissive-)
    else()
        target_compile_options(lob_core PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()

add_executable(orderbook_replay src/replay_main.cpp)
target_link_libraries(orderbook_replay PRIVATE lob_core)

add_executable(orderbook_benchmark benchmarks/orderbook_benchmark.cpp)
target_link_libraries(orderbook_benchmark PRIVATE lob_core)

add_executable(market_maker_sim simulations/market_maker_sim.cpp)
target_link_libraries(market_maker_sim PRIVATE lob_core)

if(LOB_ENABLE_WARNINGS)
    if(MSVC)
        target_compile_options(orderbook_replay PRIVATE /W4 /permissive-)
        target_compile_options(orderbook_benchmark PRIVATE /W4 /permissive-)
        target_compile_options(market_maker_sim PRIVATE /W4 /permissive-)
    else()
        target_compile_options(orderbook_replay PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(orderbook_benchmark PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(market_maker_sim PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()

include(CTest)

if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)

    include(FetchContent)

    set(CATCH_INSTALL_DOCS OFF CACHE BOOL "" FORCE)
    set(CATCH_INSTALL_EXTRAS OFF CACHE BOOL "" FORCE)

    FetchContent_Declare(
        Catch2
        URL https://github.com/catchorg/Catch2/archive/refs/tags/v3.7.1.tar.gz
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )

    FetchContent_MakeAvailable(Catch2)

    add_executable(lob_tests
        tests/csv_replay_tests.cpp
        tests/market_maker_simulation_tests.cpp
        tests/matching_engine_tests.cpp
        tests/simulation_accounting_tests.cpp
    )

    target_link_libraries(lob_tests PRIVATE lob_core Catch2::Catch2WithMain)

    if(LOB_ENABLE_WARNINGS)
        if(MSVC)
            target_compile_options(lob_tests PRIVATE /W4 /permissive-)
        else()
            target_compile_options(lob_tests PRIVATE -Wall -Wextra -Wpedantic)
        endif()
    endif()

    list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
    include(Catch)
    catch_discover_tests(lob_tests WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

    add_test(
        NAME "itch replay parser is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/itch_replay_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "itch intensity calibration gate is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/itch_intensity_calibration_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "itch intensity exponential fit is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/fit_itch_intensity_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "seed statistics aggregation is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/seed_statistics_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "queue position diagnostics aggregation is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/queue_position_diagnostics_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "fill rate diagnostics aggregation is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/fill_rate_diagnostics_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "fill rate artifact validator is deterministic"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/fill_rate_artifact_validator_tests.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )

    add_test(
        NAME "markdown links resolve"
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/check_markdown_links.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
endif()
