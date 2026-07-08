#include "navibar.h"
#include <QFont>
#include <QSizePolicy>

NaviBar::NaviBar(QWidget *parent) : QWidget(parent)
{
    setMinimumHeight(62);
    setMaximumHeight(82);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setAttribute(Qt::WA_StyledBackground, true);

    QHBoxLayout *layout = new QHBoxLayout(this);
    layout->setContentsMargins(8, 6, 8, 6);
    layout->setSpacing(8);

    const QStringList names = {"首页", "评估", "训练", "记录", "医疗建议", "设置"};

    for (int i = 0; i < names.size(); ++i) {
        QPushButton *btn = new QPushButton(this);
        btn->setMinimumSize(90, 48);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        btn->setText(names[i]);       // 修复“首页\n首页”“评估\n评估”等重复显示
        btn->setCheckable(true);
        btn->setChecked(i == 0);
        connect(btn, &QPushButton::clicked, this, [this, i]() {
            emit pageSwitched(i);
        });
        m_btns.append(btn);
        layout->addWidget(btn, 1);
    }

    setActiveIndex(0);
}

void NaviBar::setActiveIndex(int index)
{
    m_currentIndex = index;
    for (int i = 0; i < m_btns.size(); ++i) {
        m_btns[i]->setChecked(i == index);
    }
}
