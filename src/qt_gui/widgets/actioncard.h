#ifndef ACTIONCARD_H
#define ACTIONCARD_H

#include <QWidget>
#include <QLabel>
#include <QVBoxLayout>

struct ActionInfo {
    int     id;
    int     level;       // 1-4
    QString name;
    QString target;      // 目标关节
    int     difficulty;   // 1-5星
    QString description;
    QString color;       // 级别颜色
};

class ActionCard : public QWidget
{
    Q_OBJECT
public:
    explicit ActionCard(const ActionInfo &info, QWidget *parent = nullptr);

    void setSelected(bool sel);
    const ActionInfo& info() const { return m_info; }

signals:
    void clicked(int actionId);

protected:
    void mousePressEvent(QMouseEvent *) override;
    void paintEvent(QPaintEvent *) override;

private:
    ActionInfo m_info;
    bool m_selected = false;
};

#endif // ACTIONCARD_H
