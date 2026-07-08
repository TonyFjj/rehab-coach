#include "radarchart.h"
#include "utils/fontscale.h"
#include <QPainter>
#include <QPainterPath>
#include <QFontMetrics>
#include <QtMath>

namespace {

struct DimSpec {
    QString english;
    double maxPoints;
};

const DimSpec kDimSpecs[] = {
    {QStringLiteral("range_of_motion"), 30.0},
    {QStringLiteral("smoothness"), 25.0},
    {QStringLiteral("tremor"), 20.0},
    {QStringLiteral("symmetry"), 15.0},
    {QStringLiteral("speed"), 5.0},
    {QStringLiteral("endurance"), 5.0},
    {QStringLiteral("fatigue"), 5.0},
};

const QStringList kCnNames = {
    QStringLiteral("抬举幅度"),
    QStringLiteral("运动平滑度"),
    QStringLiteral("震颤程度"),
    QStringLiteral("双侧对称性"),
    QStringLiteral("运动速度"),
    QStringLiteral("运动耐力"),
};

double maxPointsForKey(const QString &key)
{
    for (int i = 0; i < int(sizeof(kDimSpecs) / sizeof(kDimSpecs[0])); ++i) {
        if (key == kDimSpecs[i].english) {
            return kDimSpecs[i].maxPoints;
        }
    }
    for (int i = 0; i < kCnNames.size() && i < 6; ++i) {
        if (key == kCnNames[i]) {
            return kDimSpecs[i].maxPoints;
        }
    }
    return 0.0;
}

double toDisplayRatio(const QString &key, double v)
{
    const double maxPts = maxPointsForKey(key);
    if (maxPts <= 0.0) {
        if (v > 1.0) {
            return qBound(0.0, v / 100.0, 1.0);
        }
        return qBound(0.0, v, 1.0);
    }

    if (v > 1.0) {
        return qBound(0.0, v / maxPts, 1.0);
    }

    const double impliedPoints = v * 100.0;
    if (impliedPoints >= 1.0 && impliedPoints <= maxPts + 0.01
        && qAbs(impliedPoints - qRound(impliedPoints)) < 0.05) {
        return qBound(0.0, impliedPoints / maxPts, 1.0);
    }
    return qBound(0.0, v, 1.0);
}

void mapEnglishKeys(QMap<QString, double> *values)
{
    for (int i = 0; i < 6; ++i) {
        const QString en = kDimSpecs[i].english;
        const QString cn = kCnNames[i];
        double v = 0.0;
        if (values->contains(en)) {
            v = values->value(en);
        } else if (values->contains(cn)) {
            v = values->value(cn);
        } else {
            continue;
        }
        const double ratio = toDisplayRatio(en, v);
        values->insert(en, ratio);
        values->insert(cn, ratio);
    }
}

Qt::Alignment labelAlignmentForAngle(double deg)
{
    double norm = std::fmod(deg + 360.0, 360.0);
    if (norm >= 330.0 || norm < 30.0) {
        return Qt::AlignBottom | Qt::AlignHCenter;
    }
    if (norm < 90.0) {
        return Qt::AlignLeft | Qt::AlignVCenter;
    }
    if (norm < 150.0) {
        return Qt::AlignLeft | Qt::AlignTop;
    }
    if (norm < 210.0) {
        return Qt::AlignTop | Qt::AlignHCenter;
    }
    if (norm < 270.0) {
        return Qt::AlignRight | Qt::AlignTop;
    }
    return Qt::AlignRight | Qt::AlignVCenter;
}

QRectF labelRectForPoint(const QPointF &pt, const QSizeF &textSize,
                         Qt::Alignment align, double gap)
{
    double x = pt.x();
    double y = pt.y();
    const double w = textSize.width();
    const double h = textSize.height();

    if (align & Qt::AlignHCenter) {
        x -= w * 0.5;
    } else if (align & Qt::AlignRight) {
        x -= w + gap;
    } else {
        x += gap;
    }

    if (align & Qt::AlignVCenter) {
        y -= h * 0.5;
    } else if (align & Qt::AlignBottom) {
        y -= h + gap;
    } else {
        y += gap;
    }

    return QRectF(x, y, w, h);
}

} // namespace

RadarChart::RadarChart(QWidget *parent) : QWidget(parent)
{
    setMinimumSize(220, 220);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
}

void RadarChart::setDimensions(const QStringList &names)
{
    m_dimNames = names;
    update();
}

void RadarChart::setValues(const QMap<QString, double> &vals)
{
    m_values.clear();
    for (auto it = vals.constBegin(); it != vals.constEnd(); ++it) {
        if (it.key().startsWith(QStringLiteral("block_"))) {
            continue;
        }
        m_values.insert(it.key(), toDisplayRatio(it.key(), it.value()));
    }
    mapEnglishKeys(&m_values);
    update();
}

void RadarChart::clear()
{
    m_values.clear();
    update();
}

void RadarChart::paintEvent(QPaintEvent *)
{
    if (m_dimNames.isEmpty()) {
        return;
    }

    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    const int n = m_dimNames.size();
    const int side = qMin(width(), height());
    const FontScale *fs = FontScale::instance();
    const bool large = fs->largeMode();
    const bool compact = side < (large ? 300 : 240);

    QFont labelFont = p.font();
    labelFont.setPixelSize(fs->px(compact ? 11 : 13));
    labelFont.setBold(true);
    QFontMetrics labelFm(labelFont);

    double maxLabelW = 0.0;
    double maxLabelH = 0.0;
    for (const QString &name : m_dimNames) {
        const QRect br = labelFm.boundingRect(
            QRect(0, 0, 200, 200), Qt::AlignCenter | Qt::TextWordWrap, name);
        maxLabelW = qMax(maxLabelW, double(br.width()));
        maxLabelH = qMax(maxLabelH, double(br.height()));
    }

    const double padScale = large ? 1.35 : 1.0;
    const double edgePad = qMax(12.0, maxLabelW * 0.6 * padScale + (large ? 16.0 : 8.0));
    const double topPad = qMax(edgePad, maxLabelH * padScale + 8.0);
    const QRectF area(
        edgePad, topPad,
        width() - edgePad * 2.0,
        height() - edgePad - topPad * 0.9
    );
    const double cx = area.center().x();
    const double cy = area.center().y();
    const double chartSide = qMin(area.width(), area.height());
    const double R = qMax(28.0, chartSide * (large ? 0.36 : 0.42));
    const double dotR = qMax(4.0, chartSide * 0.022);

    for (int ring = 1; ring <= 5; ++ring) {
        const double r = R * ring / 5.0;
        p.setPen(QPen(QColor("#D0DDE8"), ring == 5 ? 1.5 : 1.0));
        QPainterPath path;
        for (int i = 0; i <= n; ++i) {
            const double angle = qDegreesToRadians(-90.0 + 360.0 * (i % n) / n);
            const double x = cx + r * qCos(angle);
            const double y = cy + r * qSin(angle);
            if (i == 0) {
                path.moveTo(x, y);
            } else {
                path.lineTo(x, y);
            }
        }
        p.drawPath(path);

        if (ring == 5 && !compact && !large) {
            QFont ringFont = p.font();
            ringFont.setPixelSize(fs->px(10));
            p.setFont(ringFont);
            p.setPen(QColor("#95A5A6"));
            p.drawText(QRectF(cx - 16, cy - r - 14, 32, 14),
                       Qt::AlignCenter, QStringLiteral("100%"));
        }
    }

    p.setPen(QPen(QColor("#D0DDE8"), 1));
    for (int i = 0; i < n; ++i) {
        const double angle = qDegreesToRadians(-90.0 + 360.0 * i / n);
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + R * qCos(angle), cy + R * qSin(angle)));
    }

    QPainterPath dataPath;
    QList<QPointF> dataPoints;
    QList<double> ratios;

    for (int i = 0; i <= n; ++i) {
        const int idx = i % n;
        const QString &dim = m_dimNames[idx];
        const double ratio = qBound(
            0.0, toDisplayRatio(dim, m_values.value(dim, 0.0)), 1.0);
        ratios.append(ratio);

        const double angle = qDegreesToRadians(-90.0 + 360.0 * idx / n);
        const double x = cx + R * ratio * qCos(angle);
        const double y = cy + R * ratio * qSin(angle);
        dataPoints.append(QPointF(x, y));
        if (i == 0) {
            dataPath.moveTo(x, y);
        } else {
            dataPath.lineTo(x, y);
        }
    }

    p.setPen(Qt::NoPen);
    p.setBrush(QColor(46, 134, 193, 90));
    p.drawPath(dataPath);

    p.setPen(QPen(QColor("#2E86C1"), compact ? 2.0 : 3.0));
    p.setBrush(Qt::NoBrush);
    p.drawPath(dataPath);

    QFont scoreFont = p.font();
    scoreFont.setPixelSize(fs->px(compact ? 10 : qMax(11, int(side * 0.028))));
    scoreFont.setBold(true);
    p.setFont(scoreFont);
    QFontMetrics scoreFm(scoreFont);

    for (int i = 0; i < n; ++i) {
        const QPointF pt = dataPoints[i];
        const double ratio = ratios[i];

        p.setPen(QPen(Qt::white, 2.0));
        p.setBrush(QColor("#2E86C1"));
        p.drawEllipse(pt, dotR, dotR);

        const int pct = qBound(0, qRound(ratio * 100.0), 100);
        const QString scoreText = QStringLiteral("%1%").arg(pct);

        const double angle = qDegreesToRadians(-90.0 + 360.0 * i / n);
        const double inward = qMax(14.0, dotR + 12.0);
        const double sx = cx + (R * ratio - inward) * qCos(angle);
        const double sy = cy + (R * ratio - inward) * qSin(angle);
        const QSizeF scoreSize = scoreFm.size(
            Qt::TextSingleLine, scoreText);
        p.setPen(QColor("#1A5276"));
        p.drawText(
            QRectF(sx - scoreSize.width() * 0.5,
                   sy - scoreSize.height() * 0.5,
                   scoreSize.width(), scoreSize.height()),
            Qt::AlignCenter, scoreText);
    }

    if (!compact && !large) {
        QFont subFont = p.font();
        subFont.setPixelSize(fs->px(qMax(9, int(side * 0.022))));
        subFont.setBold(false);
        p.setFont(subFont);
        p.setPen(QColor("#607D8B"));
        for (int i = 0; i < n; ++i) {
            const double ratio = ratios[i];
            const double maxPts = maxPointsForKey(m_dimNames[i]);
            if (maxPts <= 0.0) {
                continue;
            }
            const int got = qRound(ratio * maxPts);
            const int full = qRound(maxPts);
            const double angle = qDegreesToRadians(-90.0 + 360.0 * i / n);
            const double inward = qMax(26.0, dotR + 24.0);
            const double lx = cx + (R * ratio - inward) * qCos(angle);
            const double ly = cy + (R * ratio - inward) * qSin(angle);
            p.drawText(QRectF(lx - 24, ly - 8, 48, 16), Qt::AlignCenter,
                       QStringLiteral("%1/%2").arg(got).arg(full));
        }
    }

    p.setFont(labelFont);
    p.setPen(QColor("#1B2631"));
    const double nameRadius = R + (large ? 34.0 : (compact ? 16.0 : 20.0));
    const double labelGap = large ? 6.0 : (compact ? 2.0 : 4.0);

    for (int i = 0; i < n; ++i) {
        const double deg = -90.0 + 360.0 * i / n;
        const double angle = qDegreesToRadians(deg);
        const QPointF anchor(
            cx + nameRadius * qCos(angle),
            cy + nameRadius * qSin(angle));
        const QString &name = m_dimNames[i];
        const Qt::Alignment align = labelAlignmentForAngle(deg);
        const double boxW = qMax(48.0, maxLabelW + 8.0);
        const double boxH = qMax(18.0, maxLabelH + 4.0);
        const QRectF textRect = labelRectForPoint(
            anchor, QSizeF(boxW, boxH), align, labelGap);
        p.drawText(textRect, align | Qt::TextWordWrap, name);
    }
}
