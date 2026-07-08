#ifndef ACTIONDB_H
#define ACTIONDB_H

#include <QObject>
#include <QList>
#include "widgets/actioncard.h"

class ActionDB : public QObject
{
    Q_OBJECT
public:
    explicit ActionDB(QObject *parent = nullptr);
    QList<ActionInfo> actionsByLevel(int level) const;
    ActionInfo action(int id) const;
    QList<ActionInfo> allActions() const { return m_actions; }
private:
    void initActions();
    QList<ActionInfo> m_actions;
};
#endif // ACTIONDB_H
