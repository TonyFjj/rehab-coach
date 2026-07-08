#ifndef FONTSCALE_H
#define FONTSCALE_H

#include <QObject>
#include <QString>

class QApplication;

/** 全局字号缩放：标准 / 大字（适老）一键切换 */
class FontScale : public QObject
{
    Q_OBJECT
public:
    static FontScale *instance();

    bool largeMode() const { return m_largeMode; }
    void setLargeMode(bool on, bool persist = true);
    void loadFromSettings();

    /** 将设计稿 px 按当前模式缩放 */
    int px(int basePx) const;
    int appPointSize() const;

    void applyApplicationFont(QApplication *app, const QString &family = QString());

    /** 与设置页 IMU/双目标定按钮一致的操作按钮样式 */
    QString actionButtonStyle(const QString &background, int baseFontPx = 14) const;

signals:
    void changed();

private:
    explicit FontScale(QObject *parent = nullptr);
    void saveToSettings() const;

    bool m_largeMode = false;
};

#endif // FONTSCALE_H
