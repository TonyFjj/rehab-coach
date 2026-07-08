#ifndef ELDERUX_H
#define ELDERUX_H

#include <QString>
#include <QJsonObject>
#include "fontscale.h"
#include <QJsonObject>

namespace ElderUx {

inline QString visionOverlayBarStyle()
{
    const int fs = FontScale::instance()->px(12);
    return QStringLiteral(
        "font-size:%1px; font-weight:bold; color:#ECF0F1;"
        "background-color: rgba(0, 0, 0, 140);"
        "border:1px solid rgba(255, 255, 255, 60);"
        "border-radius:6px; padding:4px 8px;").arg(fs);
}

inline QString visionBarStyle()
{
    return visionOverlayBarStyle();
}

inline QString trainingHudLeftStyle()
{
    const int fs = FontScale::instance()->px(14);
    return QStringLiteral(
        "font-size:%1px; font-weight:bold; color:#F9FBFC;"
        "background-color: rgba(0, 0, 0, 150);"
        "border:1px solid rgba(46, 204, 113, 120);"
        "border-radius:8px; padding:6px 10px;").arg(fs);
}

inline QString hudOverlayStyle()
{
    const int fs = FontScale::instance()->px(11);
    return QStringLiteral(
        "color:#2ECC71; font-size:%1px; font-family:monospace;"
        "background-color: rgba(0, 0, 0, 130);"
        "border-radius:4px; padding:3px 7px;").arg(fs);
}

inline QString levelBtnStyle(const QString &color, bool checked)
{
    const int fs = FontScale::instance()->px(13);
    if (checked) {
        return QStringLiteral(
            "QPushButton{border:2px solid %1; border-radius:10px;"
            "background-color: rgba(0, 0, 0, 100); color:%1;"
            "font-size:%2px; font-weight:bold; padding:4px 8px;}"
        ).arg(color).arg(fs);
    }
    return QStringLiteral(
        "QPushButton{border:1px solid rgba(255,255,255,80); border-radius:10px;"
        "background-color: rgba(0, 0, 0, 70); color:#ECF0F1;"
        "font-size:%1px; font-weight:bold; padding:4px 8px;}"
        "QPushButton:hover{background-color: rgba(0, 0, 0, 110);}"
    ).arg(fs);
}

inline QString shortenForBar(const QString &text, int maxLen = 42)
{
    const QString trimmed = text.trimmed();
    if (trimmed.size() <= maxLen) {
        return trimmed;
    }
    return trimmed.left(maxLen - 1) + QStringLiteral("…");
}

inline QString visionStatusLabel(const QString &status)
{
    if (status == QStringLiteral("ok")) {
        return QStringLiteral("🟢 视觉正常");
    }
    if (status == QStringLiteral("backlight")) {
        return QStringLiteral("🟡 逆光");
    }
    if (status == QStringLiteral("multi_person")) {
        return QStringLiteral("🟡 多人");
    }
    if (status == QStringLiteral("caregiver_present")) {
        return QStringLiteral("🟢 护理协助");
    }
    if (status == QStringLiteral("occlusion")) {
        return QStringLiteral("🟡 遮挡");
    }
    if (status == QStringLiteral("degraded")) {
        return QStringLiteral("🟡 质量一般");
    }
    if (status == QStringLiteral("poor") || status == QStringLiteral("no_signal")) {
        return QStringLiteral("🔴 视觉弱");
    }
    if (status == QStringLiteral("collecting")) {
        return QStringLiteral("📷 采集中");
    }
    return QStringLiteral("📷 检测中");
}

inline QString formatVisionLine(
    const QString &statusText,
    const QString &body,
    const QString &warning)
{
    QString line = statusText;
    QString detail = warning.isEmpty() ? body : warning;
    detail = shortenForBar(detail);
    if (!detail.isEmpty()) {
        line += QStringLiteral(" ｜ ") + detail;
    }
    return line;
}

/** 双目左右拼接预览的宽高比（与后端 debug 画面一致，约 1280:360） */
inline double stereoPreviewAspect()
{
    return 3.35;
}

/** 按屏幕与面板宽度计算摄像头区域高度，避免固定 180px 在新分辨率下过 small */
inline int visionPreviewHeight(int panelWidth, int screenHeight)
{
    const int pw = qMax(320, panelWidth);
    const int fromWidth = int(pw / stereoPreviewAspect()) + 40;
    const int fromScreen = int(screenHeight * 0.22);
    return qBound(220, qMax(fromWidth, fromScreen), 380);
}

/** 训练页：首屏摄像头宜大，按视口宽度与可见高度计算（整页可滚动） */
inline int trainingVisionPreviewHeight(
    int panelWidth,
    int viewportHeight,
    int screenHeight)
{
    const int pw = qMax(320, panelWidth);
    const int fromWidth = int(pw / stereoPreviewAspect()) + 48;
    const int fromViewport = int(qMax(400, viewportHeight) * 0.44);
    const int fromScreen = int(screenHeight * 0.38);
    return qBound(300, qMax(fromWidth, qMax(fromViewport, fromScreen)), 520);
}

} // namespace ElderUx

#endif // ELDERUX_H
