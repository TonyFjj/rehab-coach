#ifndef MEDICALADVICEPAGE_H
#define MEDICALADVICEPAGE_H

#include <QLabel>
#include <QList>
#include <QMap>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWidget>
#include "models/scoreengine.h"

class MedicalAdvicePage : public QWidget
{
    Q_OBJECT
public:
    explicit MedicalAdvicePage(QWidget *parent = nullptr);
    void refresh();
    void applyFontScale();

public slots:
    // 每完成一次评估，医疗建议页新增一条“第几次评估 + 综合得分”的记录。
    void setLatestAssessment(const ScoreResult &result);

private:
    struct DimensionAdvice {
        QString key;
        QString name;
        QString weight;
        QString posture;
        QString possibleReason;
        QString training;
        QString medicineMid;
        QString severeAdvice;
        QString actionImage;
        QString actionCaption;
        QString medicineImage;
        QString medicineCaption;
    };

    struct MedicalAdviceRecord {
        int index = 0;
        ScoreResult result;
    };

    void setupUI();
    void buildListPage();
    void buildDetailPage();
    void buildDimensionDetailPage();
    void loadStoredRecords();
    void saveStoredRecords() const;
    void rebuildRecordList();
    void showRecordDetail(int recordStorageIndex);
    void showDimensionDetail(int recordStorageIndex, const QString &dimensionKey);
    void rebuildDetailPage(const MedicalAdviceRecord &record, int recordStorageIndex);
    void rebuildDimensionDetailPage(const MedicalAdviceRecord &record, const DimensionAdvice &advice);
    void clearLayout(QLayout *layout);

    QList<DimensionAdvice> allDimensionAdvices() const;
    int dimensionScore(const ScoreResult &result, const QString &key) const;
    QString scoreStatusText(int score) const;
    QString scoreStatusColor(int score) const;
    QString overallAdviceForScore(int score) const;
    QString dimensionMedicineText(const DimensionAdvice &advice, int score) const;
    QString dimensionBriefSuggestion(const DimensionAdvice &advice, int score) const;
    QString dimensionAnalysisText(const DimensionAdvice &advice, int score) const;
    QWidget *createDimensionOverviewCard(const DimensionAdvice &advice, const ScoreResult &result, int recordStorageIndex, QWidget *parent);
    QWidget *createDimensionCard(const DimensionAdvice &advice, const ScoreResult &result, QWidget *parent, bool largeImages = false);
    QWidget *createImageBox(const QString &resourcePath, const QString &caption, QWidget *parent, bool largeMode = false);

    QStackedWidget *m_stack = nullptr;

    QWidget *m_listPage = nullptr;
    QLabel *m_listTitle = nullptr;
    QLabel *m_recordSummary = nullptr;
    QScrollArea *m_recordScrollArea = nullptr;
    QWidget *m_recordContainer = nullptr;
    QVBoxLayout *m_recordLayout = nullptr;

    QWidget *m_detailPage = nullptr;
    QScrollArea *m_detailScrollArea = nullptr;
    QWidget *m_detailContent = nullptr;
    QVBoxLayout *m_detailLayout = nullptr;

    QWidget *m_dimensionPage = nullptr;
    QScrollArea *m_dimensionScrollArea = nullptr;
    QWidget *m_dimensionContent = nullptr;
    QVBoxLayout *m_dimensionLayout = nullptr;
    int m_currentRecordStorageIndex = -1;
    QString m_currentDimensionKey;

    QList<MedicalAdviceRecord> m_records;
    bool m_recordsLoaded = false;
};

#endif // MEDICALADVICEPAGE_H
