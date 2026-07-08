#include "visionpreviewwidget.h"
#include "utils/elderux.h"
#include "utils/fontscale.h"

#include <QVBoxLayout>
#include <QByteArray>
#include <QBuffer>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImageReader>
#include <QMovie>
#include <QPainter>
#include <QProgressBar>
#include <QResizeEvent>
#include <QEventLoop>
#include <QtGlobal>

namespace {

QString gifFileNameFromPath(const QString &gifPath)
{
    QString name = QFileInfo(gifPath).fileName();
    if (!name.isEmpty()) {
        return name;
    }
    const QString trimmed = gifPath.trimmed();
    const int slash = trimmed.lastIndexOf(QLatin1Char('/'));
    return slash >= 0 ? trimmed.mid(slash + 1) : trimmed;
}

QString resolveGifDiskPath(const QString &gifPath)
{
    const QString fileName = gifFileNameFromPath(gifPath);
    if (fileName.isEmpty()) {
        return QString();
    }

    const QString appDir = QCoreApplication::applicationDirPath();
    const QString envDir = qEnvironmentVariable("REHAB_GIF_DIR");
    const QStringList roots = {
        envDir,
        appDir + QStringLiteral("/res/pic/training_gifs/"),
        appDir + QStringLiteral("/../res/pic/training_gifs/"),
        appDir + QStringLiteral("/../../res/pic/training_gifs/"),
        appDir + QStringLiteral("/../../res/pic/training_gifs/"),
        appDir + QStringLiteral("/../../../src/qt_gui/res/pic/training_gifs/"),
    };
    for (const QString &root : roots) {
        if (root.isEmpty()) {
            continue;
        }
        const QString abs = QDir(root).absoluteFilePath(fileName);
        if (QFile::exists(abs)) {
            return abs;
        }
    }
    return QString();
}

QString resolveGifQrcPath(const QString &gifPath)
{
    const QString fileName = gifFileNameFromPath(gifPath);
    if (fileName.isEmpty()) {
        return QString();
    }
    if (gifPath.startsWith(QStringLiteral(":/"))) {
        return gifPath;
    }
    return QStringLiteral(":/res/pic/training_gifs/") + fileName;
}

QMovie *createGifMovie(
    const QString &gifPath,
    QObject *parent,
    QBuffer **outBuffer,
    QString *resolvedPathOut)
{
    if (outBuffer) {
        *outBuffer = nullptr;
    }

    const QString diskPath = resolveGifDiskPath(gifPath);
    if (!diskPath.isEmpty()) {
        if (resolvedPathOut) {
            *resolvedPathOut = diskPath;
        }
        return new QMovie(diskPath, QByteArray(), parent);
    }

    const QString qrcPath = resolveGifQrcPath(gifPath);
    QFile qrcFile(qrcPath);
    if (!qrcFile.open(QIODevice::ReadOnly)) {
        if (resolvedPathOut) {
            *resolvedPathOut = qrcPath;
        }
        return nullptr;
    }

    auto *buffer = new QBuffer(parent);
    buffer->setData(qrcFile.readAll());
    if (!buffer->open(QIODevice::ReadOnly)) {
        buffer->deleteLater();
        if (resolvedPathOut) {
            *resolvedPathOut = qrcPath;
        }
        return nullptr;
    }

    if (outBuffer) {
        *outBuffer = buffer;
    }
    if (resolvedPathOut) {
        *resolvedPathOut = qrcPath + QStringLiteral(" (buffer)");
    }
    return new QMovie(buffer, "GIF", parent);
}

bool gifMovieReady(QMovie *movie)
{
    if (!movie) {
        return false;
    }
    for (int i = 0; i < 40; ++i) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 30);
        if (movie->isValid() && movie->frameCount() > 0) {
            return true;
        }
        if (!movie->currentPixmap().isNull()) {
            return true;
        }
        movie->jumpToNextFrame();
    }
    return movie->isValid() || !movie->currentPixmap().isNull();
}

} // namespace

VisionPreviewWidget::VisionPreviewWidget(QWidget *parent)
    : QFrame(parent)
{
    setObjectName(QStringLiteral("visionPreviewPanel"));
    setStyleSheet(
        "QFrame#visionPreviewPanel{background:#0F1419; border:1px solid #2C3E50;"
        "border-radius:12px;}");

    QVBoxLayout *lay = new QVBoxLayout(this);
    lay->setContentsMargins(4, 4, 4, 4);
    lay->setSpacing(0);

    m_viewport = new QWidget(this);
    m_viewport->setStyleSheet("background:#000; border-radius:8px;");
    lay->addWidget(m_viewport, 1);

    m_imageLabel = new QLabel(m_viewport);
    m_imageLabel->setAlignment(Qt::AlignCenter);
    m_imageLabel->setStyleSheet("background:transparent; border:none; color:#7F8C8D;");
    m_imageLabel->setText(QStringLiteral("等待摄像头画面…"));

    m_gifOverlayLabel = new QLabel(m_viewport);
    m_gifOverlayLabel->setAlignment(Qt::AlignCenter);
    m_gifOverlayLabel->setScaledContents(false);
    m_gifOverlayLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_gifOverlayLabel->setStyleSheet("background:#000; border:none;");
    m_gifOverlayLabel->hide();

    m_topRightLabel = new QLabel(m_viewport);
    m_topRightLabel->setStyleSheet(ElderUx::hudOverlayStyle());
    m_topRightLabel->setAlignment(Qt::AlignRight | Qt::AlignTop);
    m_topRightLabel->setWordWrap(true);
    m_topRightLabel->hide();

    m_topLeftLabel = new QLabel(m_viewport);
    m_topLeftLabel->setStyleSheet(ElderUx::trainingHudLeftStyle());
    m_topLeftLabel->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    m_topLeftLabel->setWordWrap(true);
    m_topLeftLabel->hide();

    m_topBarLabel = new QLabel(m_viewport);
    m_topBarLabel->setStyleSheet(ElderUx::visionOverlayBarStyle());
    m_topBarLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_topBarLabel->setWordWrap(false);
    m_topBarLabel->hide();

    m_bottomBarLabel = new QLabel(m_viewport);
    m_bottomBarLabel->setStyleSheet(ElderUx::visionOverlayBarStyle());
    m_bottomBarLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_bottomBarLabel->setWordWrap(true);
    m_bottomBarLabel->hide();

    m_topProgressBar = new QProgressBar(m_viewport);
    m_topProgressBar->setRange(0, 100);
    m_topProgressBar->setValue(0);
    m_topProgressBar->setTextVisible(true);
    m_topProgressBar->setFormat(QStringLiteral("%p%"));
    m_topProgressBar->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_topProgressBar->hide();

    m_topCountdownLabel = new QLabel(m_viewport);
    m_topCountdownLabel->setAlignment(Qt::AlignCenter);
    m_topCountdownLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_topCountdownLabel->hide();
}

void VisionPreviewWidget::setTopProgressVisible(bool visible)
{
    if (!m_topProgressBar) {
        return;
    }
    m_topProgressBar->setVisible(visible);
    repositionOverlays();
}

void VisionPreviewWidget::setTopCountdownVisible(bool visible)
{
    if (!m_topCountdownLabel) {
        return;
    }
    m_topCountdownLabel->setVisible(visible);
    repositionOverlays();
}

void VisionPreviewWidget::refreshOverlays()
{
    repositionOverlays();
}

void VisionPreviewWidget::setTopRightText(const QString &text)
{
    if (!m_topRightLabel) {
        return;
    }
    if (text.isEmpty()) {
        m_topRightLabel->hide();
    } else {
        m_topRightLabel->setText(text);
        m_topRightLabel->show();
    }
    repositionOverlays();
}

void VisionPreviewWidget::setTopLeftText(const QString &text)
{
    if (!m_topLeftLabel) {
        return;
    }
    if (text.isEmpty()) {
        m_topLeftLabel->hide();
        repositionOverlays();
        return;
    }
    m_topLeftLabel->setText(text);
    m_topLeftLabel->show();
    repositionOverlays();
}

void VisionPreviewWidget::setTopBarText(const QString &text)
{
    if (!m_topBarLabel) {
        return;
    }
    if (text.isEmpty()) {
        m_topBarLabel->hide();
        repositionOverlays();
        return;
    }
    m_topBarLabel->setText(text);
    m_topBarLabel->show();
    repositionOverlays();
}

void VisionPreviewWidget::setBottomBarText(const QString &text)
{
    if (!m_bottomBarLabel) {
        return;
    }
    if (text.isEmpty()) {
        m_lastBottomBarText.clear();
        m_bottomBarLabel->hide();
        repositionOverlays();
        return;
    }
    if (text == m_lastBottomBarText) {
        return;
    }
    m_lastBottomBarText = text;
    m_bottomBarLabel->setText(text);
    m_bottomBarLabel->show();
    repositionOverlays();
}

void VisionPreviewWidget::setRightCameraGif(const QString &gifPath)
{
    if (!m_gifOverlayLabel) {
        return;
    }
    if (gifPath == m_currentGifPath && m_gifMovie) {
        refreshScaledPixmap();
        return;
    }

    if (m_gifMovie) {
        disconnect(m_gifMovie, nullptr, this, nullptr);
        m_gifMovie->stop();
        m_gifMovie->deleteLater();
        m_gifMovie = nullptr;
    }
    if (m_gifBuffer) {
        m_gifBuffer->deleteLater();
        m_gifBuffer = nullptr;
    }

    m_currentGifPath = gifPath;
    if (gifPath.isEmpty()) {
        m_gifOverlayLabel->clear();
        m_gifOverlayLabel->hide();
        refreshScaledPixmap();
        return;
    }

    QString resolvedPath;
    m_gifMovie = createGifMovie(gifPath, this, &m_gifBuffer, &resolvedPath);
    if (!m_gifMovie) {
        qWarning("VisionPreview: cannot open GIF %s (tried %s)",
                 qPrintable(gifPath), qPrintable(resolvedPath));
        m_currentGifPath.clear();
        refreshScaledPixmap();
        return;
    }

    m_gifMovie->setCacheMode(QMovie::CacheAll);
    m_gifMovie->start();
    if (!gifMovieReady(m_gifMovie)) {
        qWarning("VisionPreview: invalid GIF %s (resolved %s)",
                 qPrintable(gifPath), qPrintable(resolvedPath));
        m_gifMovie->deleteLater();
        m_gifMovie = nullptr;
        if (m_gifBuffer) {
            m_gifBuffer->deleteLater();
            m_gifBuffer = nullptr;
        }
        m_currentGifPath.clear();
        refreshScaledPixmap();
        return;
    }

    qInfo("VisionPreview: GIF loaded from %s", qPrintable(resolvedPath));
    connect(m_gifMovie, &QMovie::frameChanged, this, [this](int) {
        refreshScaledPixmap();
    });
    refreshScaledPixmap();
}

void VisionPreviewWidget::clearRightCameraGif()
{
    setRightCameraGif(QString());
}

void VisionPreviewWidget::updatePreview(const QJsonObject &payload)
{
    const QString b64 = payload.value(QStringLiteral("image")).toString();
    if (b64.isEmpty()) {
        return;
    }

    const QByteArray raw = QByteArray::fromBase64(b64.toLatin1());
    QPixmap pix;
    if (!pix.loadFromData(raw, "JPEG")) {
        m_sourcePixmap = QPixmap();
        m_imageLabel->setPixmap(QPixmap());
        m_imageLabel->setText(QStringLiteral("画面解码失败"));
        return;
    }

    m_sourcePixmap = pix;
    m_imageLabel->setText(QString());
    refreshScaledPixmap();
    repositionOverlays();
}

void VisionPreviewWidget::clearPreview()
{
    m_sourcePixmap = QPixmap();
    m_lastBottomBarText.clear();
    m_imageLabel->clear();
    m_imageLabel->setText(QStringLiteral("等待摄像头画面…"));
}

void VisionPreviewWidget::resizeEvent(QResizeEvent *event)
{
    QFrame::resizeEvent(event);
    refreshScaledPixmap();
    repositionOverlays();
}

void VisionPreviewWidget::refreshScaledPixmap()
{
    if (!m_viewport || !m_imageLabel) {
        return;
    }

    m_imageLabel->setGeometry(m_viewport->rect());

    if (m_sourcePixmap.isNull()) {
        return;
    }

    const QSize target = m_viewport->size();
    if (target.width() < 8 || target.height() < 8) {
        return;
    }

    int dispW = target.width();
    int dispH = qMax(1, int(dispW / ElderUx::stereoPreviewAspect()));
    if (dispH > target.height()) {
        dispH = target.height();
        dispW = qMax(1, int(dispH * ElderUx::stereoPreviewAspect()));
    }

    const bool useGifPanel = m_gifMovie && !m_currentGifPath.isEmpty();
    QPixmap display(dispW, dispH);
    display.fill(Qt::black);

    QPainter painter(&display);
    painter.setRenderHint(QPainter::SmoothPixmapTransform, true);

    const int srcW = m_sourcePixmap.width();
    const int srcH = m_sourcePixmap.height();
    if (srcW < 2 || srcH < 1) {
        return;
    }

    if (useGifPanel) {
        const int halfSrcW = srcW / 2;
        QPixmap leftCam = m_sourcePixmap.copy(0, 0, halfSrcW, srcH);
        const int panelW = dispW / 2;
        const int panelH = dispH;
        QPixmap leftScaled = leftCam.scaled(
            panelW, panelH, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        const int lx = (panelW - leftScaled.width()) / 2;
        const int ly = (panelH - leftScaled.height()) / 2;
        painter.drawPixmap(lx, ly, leftScaled);

        QPixmap gifFrame = m_gifMovie->currentPixmap();
        if (!gifFrame.isNull()) {
            QPixmap gifScaled = gifFrame.scaled(
                panelW, panelH, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
            const int gx = panelW + (panelW - gifScaled.width()) / 2;
            const int gy = (panelH - gifScaled.height()) / 2;
            painter.drawPixmap(gx, gy, gifScaled);
        } else {
            painter.fillRect(panelW, 0, panelW, panelH, QColor(20, 20, 20));
            painter.setPen(QColor(127, 140, 141));
            painter.drawText(QRect(panelW, 0, panelW, panelH),
                             Qt::AlignCenter,
                             QStringLiteral("加载示范动画…"));
        }
        painter.setPen(QColor(255, 0, 0));
        painter.drawLine(panelW, 0, panelW, panelH);
    } else {
        QPixmap scaled = m_sourcePixmap.scaled(
            dispW, dispH, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        const int x = (dispW - scaled.width()) / 2;
        const int y = (dispH - scaled.height()) / 2;
        painter.drawPixmap(x, y, scaled);
    }
    painter.end();

    m_imageLabel->setPixmap(display);
    m_gifOverlayLabel->hide();
}

void VisionPreviewWidget::repositionOverlays()
{
    if (!m_viewport) {
        return;
    }

    const int w = m_viewport->width();
    const int h = m_viewport->height();
    const int pad = 8;
    const int gap = 8;
    const int barH = qMax(26, FontScale::instance()->px(13) + 10);

    if (m_topBarLabel && m_topBarLabel->isVisible()) {
        m_topBarLabel->setGeometry(pad, pad, w - pad * 2, barH);
        m_topBarLabel->raise();
    }

    int topRowY = pad;
    int topRowH = barH;
    int rightW = 0;
    int countdownW = 0;

    if (m_topRightLabel && m_topRightLabel->isVisible()) {
        m_topRightLabel->adjustSize();
        rightW = qMin(w / 2, qMax(120, m_topRightLabel->sizeHint().width() + 12));
        topRowH = qMax(topRowH, m_topRightLabel->sizeHint().height() + 8);
    }

    if (m_topCountdownLabel && m_topCountdownLabel->isVisible()) {
        m_topCountdownLabel->adjustSize();
        countdownW = qMax(72, m_topCountdownLabel->sizeHint().width() + 16);
        topRowH = qMax(topRowH, m_topCountdownLabel->sizeHint().height() + 8);
    }

    int cursorX = w - pad;
    if (m_topRightLabel && m_topRightLabel->isVisible()) {
        cursorX -= rightW;
        m_topRightLabel->setGeometry(cursorX, topRowY, rightW, topRowH);
        m_topRightLabel->raise();
        cursorX -= gap;
    }

    if (m_topCountdownLabel && m_topCountdownLabel->isVisible()) {
        cursorX -= countdownW;
        m_topCountdownLabel->setGeometry(cursorX, topRowY, countdownW, topRowH);
        m_topCountdownLabel->raise();
        cursorX -= gap;
    }

    if (m_topProgressBar && m_topProgressBar->isVisible()) {
        const int progW = qMax(80, cursorX - pad);
        m_topProgressBar->setGeometry(pad, topRowY, progW, topRowH);
        m_topProgressBar->raise();
    }

    int leftTop = topRowY + topRowH + gap;
    if (m_topLeftLabel && m_topLeftLabel->isVisible()) {
        m_topLeftLabel->adjustSize();
        const int lw = qMin(w / 2 - pad, qMax(140, m_topLeftLabel->sizeHint().width() + 16));
        const int lh = qMax(48, m_topLeftLabel->sizeHint().height() + 8);
        m_topLeftLabel->setGeometry(pad, leftTop, lw, lh);
        m_topLeftLabel->raise();
    }

    if (m_bottomBarLabel && m_bottomBarLabel->isVisible()) {
        m_bottomBarLabel->adjustSize();
        const int bh = qMax(barH + 4, m_bottomBarLabel->sizeHint().height() + 8);
        m_bottomBarLabel->setGeometry(pad, h - bh - pad, w - pad * 2, bh);
        m_bottomBarLabel->raise();
    }
}

QRect VisionPreviewWidget::previewImageRect() const
{
    if (!m_viewport) {
        return QRect();
    }

    const QSize target = m_viewport->size();
    if (target.width() < 8 || target.height() < 8) {
        return QRect();
    }

    if (m_sourcePixmap.isNull()) {
        return m_viewport->rect();
    }

    int dispW = target.width();
    int dispH = qMax(1, int(dispW / ElderUx::stereoPreviewAspect()));
    if (dispH > target.height()) {
        dispH = target.height();
        dispW = qMax(1, int(dispH * ElderUx::stereoPreviewAspect()));
    }

    const int x = (target.width() - dispW) / 2;
    const int y = (target.height() - dispH) / 2;
    return QRect(x, y, dispW, dispH);
}

void VisionPreviewWidget::updateGifOverlay()
{
    refreshScaledPixmap();
}
