#include "arcgauge.h"
#include <QPainter>
#include <QPen>
#include <QBrush>
#include <QFont>
#include <QtMath>

ArcGauge::ArcGauge(QWidget *parent) : QWidget(parent)
{
    setMinimumSize(300, 230);
}

void ArcGauge::setValue(int v)
{
    m_value = qBound(0, v, 100);
    update();
    emit valueChanged(m_value);
}

void ArcGauge::setLevel(const QString &level)
{
    m_level = level;
    update();
}

void ArcGauge::setLevelColor(const QColor &c)
{
    m_levelColor = c;
    update();
}

void ArcGauge::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    int w = width(), h = height();
    int side = qMin(w, h);
    p.translate(w / 2.0, h / 2.0 + 28);

    // 参数
    double radius = side * 0.42;
    double penWidth = side * 0.065;
    double startAngle = 210.0;
    double spanAngle = -240.0;

    // 背景弧
    QPen bgPen(QColor("#E0E0E0"), penWidth, Qt::SolidLine, Qt::RoundCap);
    p.setPen(bgPen);
    p.drawArc(QRectF(-radius, -radius, 2*radius, 2*radius),
              qRound(startAngle * 16), qRound(spanAngle * 16));

    // 前景弧（根据分值着色）
    double ratio = m_value / 100.0;
    double valueAngle = spanAngle * ratio;

    QColor arcColor = m_levelColor;
    QPen fgPen(arcColor, penWidth, Qt::SolidLine, Qt::RoundCap);
    p.setPen(fgPen);
    p.drawArc(QRectF(-radius, -radius, 2*radius, 2*radius),
              qRound(startAngle * 16), qRound(valueAngle * 16));

    // 中心数值
    QFont numFont("Microsoft YaHei", qRound(side * 0.18), QFont::Bold);
    p.setFont(numFont);
    p.setPen(QColor("#1B2631"));
    p.drawText(QRectF(-radius, -radius * 0.5, 2*radius, radius * 0.8),
               Qt::AlignCenter, QString::number(m_value));

    // 级别文字
    QFont lvlFont("Microsoft YaHei", qRound(side * 0.075));
    p.setFont(lvlFont);
    p.setPen(arcColor);
    p.drawText(QRectF(-radius, radius * 0.15, 2*radius, radius * 0.4),
               Qt::AlignCenter, m_level);

    // 刻度标注 0 和 100
    QFont tickFont("Microsoft YaHei", qRound(side * 0.05));
    p.setFont(tickFont);
    p.setPen(QColor("#A0A0A0"));

    // 0位置（左下）
    double angle0 = qDegreesToRadians(startAngle);
    double tx0 = (radius + penWidth) * qCos(angle0);
    double ty0 = -(radius + penWidth) * qSin(angle0);
    p.drawText(QRectF(tx0 - 20, ty0 - 10, 40, 20), Qt::AlignCenter, "0");

    // 100位置（右下）
    double angle100 = qDegreesToRadians(startAngle + spanAngle);
    double tx100 = (radius + penWidth) * qCos(angle100);
    double ty100 = -(radius + penWidth) * qSin(angle100);
    p.drawText(QRectF(tx100 - 25, ty100 - 10, 50, 20), Qt::AlignCenter, "100");
}
