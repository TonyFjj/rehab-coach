#ifndef LLMBRIDGE_H
#define LLMBRIDGE_H

#include <QObject>
#include <QLocalSocket>
#include <QTimer>

class LlmBridge : public QObject
{
    Q_OBJECT
public:
    explicit LlmBridge(QObject *parent = nullptr);
    void requestGuidance(const QString &actionName, double angleError, const QString &phase);

signals:
    void guidanceReady(const QString &text);
    void connectionChanged(bool connected);

private slots:
    void onReadyRead();
    void onConnected();
    void onDisconnected();

private:
    QLocalSocket *m_socket;
    QTimer *m_reconnectTimer;
    void tryConnect();
};
#endif // LLMBRIDGE_H
