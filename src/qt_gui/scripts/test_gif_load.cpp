#include <QCoreApplication>
#include <QImageReader>
#include <QMovie>
#include <QPixmap>
#include <QFile>
#include <QDebug>

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    const QString path = argc > 1 ? QString::fromLocal8Bit(argv[1])
                                  : QStringLiteral("build-linux/res/pic/training_gifs/坐姿肩关节主动前屈.gif");

    qInfo("QT_PLUGIN_PATH=%s", qPrintable(qEnvironmentVariable("QT_PLUGIN_PATH")));
    qInfo("Testing GIF: %s exists=%d", qPrintable(path), QFile::exists(path));

    QImageReader reader(path);
    qInfo("QImageReader canRead=%d error=%s", reader.canRead(), qPrintable(reader.errorString()));
    const QImage img = reader.read();
    qInfo("QImageReader frame0: null=%d size=%dx%d",
          img.isNull(), img.width(), img.height());

    QMovie movie(path);
    movie.setCacheMode(QMovie::CacheAll);
    movie.start();
    for (int i = 0; i < 30; ++i) {
        app.processEvents();
        if (!movie.currentPixmap().isNull() || (movie.isValid() && movie.frameCount() > 0)) {
            qInfo("QMovie OK: valid=%d frames=%d size=%dx%d",
                  movie.isValid(), movie.frameCount(),
                  movie.currentPixmap().width(), movie.currentPixmap().height());
            return 0;
        }
        movie.jumpToNextFrame();
    }
    qWarning("QMovie FAILED: valid=%d frames=%d lastError=%s",
             movie.isValid(), movie.frameCount(), qPrintable(movie.lastErrorString()));
    return 1;
}
