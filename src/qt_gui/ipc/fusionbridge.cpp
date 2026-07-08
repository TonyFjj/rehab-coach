#include "fusionbridge.h"
#include <cstring>

// 共享内存布局：frameIndex(4B) + timestamp(8B) + 17*3*4B joints + 17*8B imu
#pragma pack(push,1)
struct ShmLayout {
    int frameIndex;
    qint64 timestamp;
    float joints[17][3];
    double imuMicro[17];
};
#pragma pack(pop)

FusionBridge::FusionBridge(QObject *parent)
    : QObject(parent), m_shm("fusion_skeleton_shm")
{
    m_pollTimer = new QTimer(this);
    m_pollTimer->setInterval(50); // 20fps
    connect(m_pollTimer, &QTimer::timeout, this, &FusionBridge::pollFrame);
}

void FusionBridge::startListening() { m_pollTimer->start(); }
void FusionBridge::stopListening()  { m_pollTimer->stop(); }

void FusionBridge::pollFrame()
{
    if (!m_shm.isAttached()) {
        if (!m_shm.attach()) return;
    }
    m_shm.lock();
    const ShmLayout *data = reinterpret_cast<const ShmLayout*>(m_shm.constData());
    if (data->frameIndex != m_lastFrameIndex) {
        m_lastFrameIndex = data->frameIndex;
        FusionFrame frame;
        frame.timestamp = data->timestamp;
        frame.frameIndex = data->frameIndex;
        for (int i = 0; i < 17; ++i) {
            frame.joints.append(QVector3D(data->joints[i][0], data->joints[i][1], data->joints[i][2]));
            frame.imuMicroMotion.append(data->imuMicro[i]);
        }
        emit fusionFrameReady(frame);
    }
    m_shm.unlock();
}
