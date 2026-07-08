cmake_minimum_required(VERSION 3.16)

project(prograss_copy LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Widgets Network)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Widgets Network)

set(PROJECT_SOURCES
    main.cpp
    widget.cpp
    mainwindow.cpp
    pages/homepage.cpp
    pages/assessmentpage.cpp
    pages/trainingpage.cpp
    pages/recordspage.cpp
    pages/medicaladvicepage.cpp
    pages/settingspage.cpp
    widgets/arcgauge.cpp
    widgets/radarchart.cpp
    widgets/actioncard.cpp
    widgets/navibar.cpp
    widgets/visionpreviewwidget.cpp
    ipc/imubridge.cpp
    ipc/visionbridge.cpp
    ipc/llmbridge.cpp
    ipc/fusionbridge.cpp
    ipc/enginebridge.cpp
    models/scoreengine.cpp
    models/actiondb.cpp
    models/datastorage.cpp
    utils/fontscale.cpp

    widget.h
    mainwindow.h
    pages/homepage.h
    pages/assessmentpage.h
    pages/trainingpage.h
    pages/recordspage.h
    pages/medicaladvicepage.h
    pages/settingspage.h
    widgets/arcgauge.h
    widgets/radarchart.h
    widgets/actioncard.h
    widgets/navibar.h
    widgets/visionpreviewwidget.h
    ipc/imubridge.h
    ipc/visionbridge.h
    ipc/llmbridge.h
    ipc/fusionbridge.h
    ipc/enginebridge.h
    models/scoreengine.h
    models/actiondb.h
    models/datastorage.h
    utils/fontscale.h

    widget.ui
    pic.qrc
    qss.qrc
)

add_executable(prograss_copy ${PROJECT_SOURCES})

target_include_directories(prograss_copy PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/pages
    ${CMAKE_CURRENT_SOURCE_DIR}/widgets
    ${CMAKE_CURRENT_SOURCE_DIR}/models
    ${CMAKE_CURRENT_SOURCE_DIR}/ipc
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
)

target_link_libraries(prograss_copy PRIVATE
    Qt${QT_VERSION_MAJOR}::Widgets
    Qt${QT_VERSION_MAJOR}::Network
)

if(UNIX AND NOT APPLE)
    install(TARGETS prograss_copy RUNTIME DESTINATION bin)
endif()
