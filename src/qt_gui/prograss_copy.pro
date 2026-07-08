QT       += core gui widgets network

greaterThan(QT_MAJOR_VERSION, 4): QT += widgets

TARGET   = prograss_copy
TEMPLATE = app
CONFIG   += c++17
CONFIG   += resources_big
CONFIG   -= app_bundle

DEFINES += QT_DEPRECATED_WARNINGS

INCLUDEPATH += \
    $$PWD \
    $$PWD/pages \
    $$PWD/widgets \
    $$PWD/models \
    $$PWD/ipc

SOURCES += \
    main.cpp \
    widget.cpp \
    mainwindow.cpp \
    pages/homepage.cpp \
    pages/assessmentpage.cpp \
    pages/trainingpage.cpp \
    pages/recordspage.cpp \
    pages/medicaladvicepage.cpp \
    pages/settingspage.cpp \
    widgets/arcgauge.cpp \
    widgets/radarchart.cpp \
    widgets/actioncard.cpp \
    widgets/navibar.cpp \
    ipc/imubridge.cpp \
    ipc/visionbridge.cpp \
    ipc/llmbridge.cpp \
    ipc/fusionbridge.cpp \
    models/scoreengine.cpp \
    models/actiondb.cpp \
    models/datastorage.cpp

HEADERS += \
    widget.h \
    mainwindow.h \
    pages/homepage.h \
    pages/assessmentpage.h \
    pages/trainingpage.h \
    pages/recordspage.h \
    pages/medicaladvicepage.h \
    pages/settingspage.h \
    widgets/arcgauge.h \
    widgets/radarchart.h \
    widgets/actioncard.h \
    widgets/navibar.h \
    ipc/imubridge.h \
    ipc/visionbridge.h \
    ipc/llmbridge.h \
    ipc/fusionbridge.h \
    models/scoreengine.h \
    models/actiondb.h \
    models/datastorage.h

FORMS += \
    widget.ui

RESOURCES += \
    pic.qrc \
    qss.qrc

# Default rules for deployment.
qnx: target.path = /tmp/$${TARGET}/bin
else: unix:!android: target.path = $$OUT_PWD/bin
!isEmpty(target.path): INSTALLS += target
