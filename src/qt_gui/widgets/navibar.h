#ifndef NAVIBAR_H
#define NAVIBAR_H

#include <QWidget>
#include <QPushButton>
#include <QHBoxLayout>
#include <QLabel>

class NaviBar : public QWidget
{
    Q_OBJECT
public:
    explicit NaviBar(QWidget *parent = nullptr);
    void setActiveIndex(int index);

signals:
    void pageSwitched(int index);

private:
    QList<QPushButton*> m_btns;
    int m_currentIndex = 0;
};

#endif // NAVIBAR_H
