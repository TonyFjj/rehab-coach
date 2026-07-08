#ifndef IMUBRIDGE_H
#define IMUBRIDGE_H

#include <QObject>
#include <QLocalSocket>
#include <QTimer>
#include <QMap>

// IMU数据桥接：通过Unix Domain Socket连接IMU采集进程
// 传感器代码在其他进程中，Qt只负责接收数据
class ImuBridge : public QObject
{
    Q_OBJECT
public:
    explicit ImuBridge(QObject *parent = nullptr);
    void connectToImuProcess(const QString &serverName = "imu_server");
    void startAssessment();   // 发送"开始评估"指令
    void stopAssessment();    // 发送"停止评估"指令

signals:
    void imuDataReady(const QMap<QString,double> &rawData);
    void connectionChanged(bool connected);

private slots:
    void onReadyRead();
    void onConnected();
    void onDisconnected();

private:
    QLocalSocket *m_socket;
    QTimer *m_reconnectTimer;
    bool m_connected = false;
    void tryConnect();
};
#endif // IMUBRIDGE_H
