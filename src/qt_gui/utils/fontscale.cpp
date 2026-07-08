#include "fontscale.h"

#include "models/datastorage.h"

#include <QApplication>
#include <QFont>
#include <QJsonObject>
#include <QtGlobal>

FontScale *FontScale::instance()
{
    static FontScale *self = new FontScale(qApp);
    return self;
}

FontScale::FontScale(QObject *parent)
    : QObject(parent)
{
}

void FontScale::loadFromSettings()
{
    QJsonObject root;
    if (DataStorage::loadAppSettings(&root)) {
        m_largeMode = root.value(QStringLiteral("largeTextMode")).toBool(false);
    }
}

void FontScale::saveToSettings() const
{
    QJsonObject root;
    DataStorage::loadAppSettings(&root);
    root.insert(QStringLiteral("largeTextMode"), m_largeMode);
    DataStorage::saveAppSettings(root);
}

void FontScale::setLargeMode(bool on, bool persist)
{
    if (m_largeMode == on) {
        return;
    }
    m_largeMode = on;
    if (persist) {
        saveToSettings();
    }
    emit changed();
}

int FontScale::px(int basePx) const
{
    if (!m_largeMode) {
        return basePx;
    }
    return qMax(basePx + 4, int(qRound(basePx * 1.38)));
}

int FontScale::appPointSize() const
{
    return m_largeMode ? 15 : 11;
}

void FontScale::applyApplicationFont(QApplication *app, const QString &family)
{
    if (!app) {
        return;
    }
    QFont font = app->font();
    if (!family.isEmpty()) {
        font.setFamily(family);
    }
    font.setPointSize(appPointSize());
    app->setFont(font);
}

QString FontScale::actionButtonStyle(const QString &background, int baseFontPx) const
{
    return QStringLiteral(
        "QPushButton{background:%1; color:white; border:none; border-radius:10px;"
        "font-size:%2px; font-weight:bold; padding:8px 16px;}"
        "QPushButton:pressed{background:%1; opacity:0.85;}"
        "QPushButton:disabled{background:#BDC3C7; color:#ECF0F1;}")
        .arg(background)
        .arg(px(baseFontPx));
}
