#include "actioncard.h"
#include <QPainter>
#include <QMouseEvent>
#include <QSizePolicy>

ActionCard::ActionCard(const ActionInfo &info, QWidget *parent)
    : QWidget(parent), m_info(info)
{
    setMinimumSize(170, 110);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    setCursor(Qt::PointingHandCursor);

    QVBoxLayout *lay = new QVBoxLayout(this);
    lay->setContentsMargins(14, 10, 14, 10);

    QLabel *nameLbl = new QLabel(info.name);
    nameLbl->setStyleSheet("font-size:15px; font-weight:bold; color:#1B2631; border:none;");
    lay->addWidget(nameLbl);

    QLabel *targetLbl = new QLabel("目标: " + info.target);
    targetLbl->setStyleSheet("font-size:12px; color:#606060; border:none;");
    lay->addWidget(targetLbl);

    // 星级
    QString stars;
    for (int i = 0; i < 5; ++i)
        stars += (i < info.difficulty) ? QString::fromUtf8("\xe2\x98\x85") : QString::fromUtf8("\xe2\x98\x86");
    QLabel *starLbl = new QLabel("难度: " + stars);
    starLbl->setStyleSheet("font-size:12px; color:#F39C12; border:none;");
    lay->addWidget(starLbl);

    lay->addStretch();
}

void ActionCard::setSelected(bool sel)
{
    m_selected = sel;
    update();
}

void ActionCard::mousePressEvent(QMouseEvent *)
{
    emit clicked(m_info.id);
}

void ActionCard::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    QColor bg = m_selected ? QColor(m_info.color).lighter(160) : QColor("#FFFFFF");
    QColor border = m_selected ? QColor(m_info.color) : QColor("#D0DDE8");

    // 圆角矩形
    p.setPen(QPen(border, m_selected ? 3 : 1));
    p.setBrush(bg);
    p.drawRoundedRect(rect().adjusted(1,1,-1,-1), 12, 12);

    // 左侧色条
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(m_info.color));
    p.drawRoundedRect(QRect(0, 8, 5, height()-16), 2, 2);
}
