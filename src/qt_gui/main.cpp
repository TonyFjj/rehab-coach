#include "widget.h"
#include "utils/fontscale.h"
#include <QApplication>
#include <QCoreApplication>
#include <QFont>
#include <QFontDatabase>
#include <QStringList>
#include <QGuiApplication>
#include <QtGlobal>
#include <QDebug>

int main(int argc, char *argv[])
{
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
    QCoreApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
#endif
#if QT_VERSION >= QT_VERSION_CHECK(5, 14, 0)
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(
        Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
#endif

    QApplication app(argc, argv);

    qInfo("prograss_copy build 20260621-gif3 appDir=%s",
          qPrintable(QCoreApplication::applicationDirPath()));

    // 全局字体：Linux/Windows 自动选择可用中文字体，避免中文乱码或字体缺失。
    QStringList fontCandidates;
    fontCandidates << QStringLiteral("Microsoft YaHei")
                   << QStringLiteral("Noto Sans CJK SC")
                   << QStringLiteral("Source Han Sans SC")
                   << QStringLiteral("WenQuanYi Micro Hei")
                   << QStringLiteral("DejaVu Sans");
    const QStringList families = QFontDatabase().families();
    QString selectedFont = fontCandidates.last();
    for (const QString &candidate : fontCandidates) {
        if (families.contains(candidate)) {
            selectedFont = candidate;
            break;
        }
    }
    app.setFont(QFont(selectedFont, 11));

    FontScale::instance()->loadFromSettings();
    FontScale::instance()->applyApplicationFont(&app, selectedFont);

    Widget w;
    w.show();

    return app.exec();
}
