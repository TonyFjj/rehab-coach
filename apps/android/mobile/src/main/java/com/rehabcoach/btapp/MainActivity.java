package com.rehabcoach.btapp;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.rehabcoach.btapp.bluetooth.BluetoothSppClient;
import com.rehabcoach.btapp.model.RehabMessageParser;
import com.rehabcoach.btapp.model.RehabResult;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class MainActivity extends Activity implements BluetoothSppClient.Listener {
    private static final String TAG = "RehabCoachApp";
    private static final int REQ_BT_PERMISSION = 1001;
    private static final int TAB_HOME = 0;
    private static final int TAB_ADVICE = 1;
    private static final int TAB_RECORDS = 2;
    private static final int TAB_SETTINGS = 3;
    private static final String PREFS_NAME = "rehab_sync_store";
    private static final String KEY_TRAINING_RECORDS = "training_records";
    private static final String KEY_ASSESSMENT_RECORDS = "assessment_records";
    private static final int MAX_SAVED_RECORDS = 100;
    /** 用于确认是否安装了最新编译的 APK（设置页可见） */
    private static final String APP_BUILD_ID = "20260621";

    private static final int COLOR_INK = 0xFF142B2F;
    private static final int COLOR_MUTED = 0xFF65757A;
    private static final int COLOR_PAGE = 0xFFF7F8F5;
    private static final int COLOR_PRIMARY = 0xFF0E6F72;
    private static final int COLOR_PRIMARY_DARK = 0xFF0A4F52;
    private static final int COLOR_ACCENT = 0xFF7A9E65;
    private static final int COLOR_WARNING = 0xFFB7791F;
    private static final int COLOR_DANGER = 0xFFB94B43;
    private static final int COLOR_CORAL = 0xFFD66A50;

    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSppClient bluetoothClient;
    private final List<DeviceItem> devices = new ArrayList<>();
    private final LinkedHashMap<String, DeviceItem> devicesByAddress = new LinkedHashMap<>();
    private final List<RehabResult> trainingRecords = new ArrayList<>();
    private final List<RehabResult> assessmentRecords = new ArrayList<>();
    private BluetoothDevice pendingBondDevice;
    private RehabResult latestResult;
    private boolean receiverRegistered;
    private int activeTab = TAB_HOME;

    private final View[] tabPages = new View[4];
    private Button homeNavButton;
    private Button adviceNavButton;
    private Button recordsNavButton;
    private Button settingsNavButton;

    private Spinner deviceSpinner;
    private TextView statusView;
    private TextView settingsStatusSummaryView;
    private TextView settingsPermissionView;
    private TextView deviceCountView;
    private TextView homeDeviceCountView;
    private TextView connectionHelpView;
    private TextView scoreView;
    private TextView scoreCaptionView;
    private TextView levelView;
    private TextView sourceView;
    private TextView timeView;
    private TextView homeAdvicePreviewView;
    private TextView homeRecordCountView;
    private TextView homeLatestSummaryView;
    private TextView adviceMetaView;
    private TextView adviceView;
    private LinearLayout liveAdviceContainer;
    private LinearLayout knowledgeHomeContainer;
    private LinearLayout knowledgeDetailContainer;
    private TextView knowledgeDetailTitleView;
    private TextView knowledgeDetailSubtitleView;
    private LinearLayout knowledgeDetailBody;
    private TextView recordsSummaryView;
    private TextView assessmentHistorySummaryView;
    private TextView logView;
    private LinearLayout dimensionsContainer;
    private LinearLayout actionsContainer;
    private LinearLayout recordsContainer;
    private LinearLayout assessmentHistoryContainer;
    private CheckBox autoFetchCheck;

    private final BroadcastReceiver bluetoothReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (BluetoothDevice.ACTION_FOUND.equals(action)) {
                BluetoothDevice device = getBluetoothDeviceExtra(intent);
                short rssi = intent.getShortExtra(BluetoothDevice.EXTRA_RSSI, Short.MIN_VALUE);
                if (device != null) {
                    addOrUpdateDevice(device, false, rssi);
                    updateDeviceSpinner();
                }
            } else if (BluetoothAdapter.ACTION_DISCOVERY_STARTED.equals(action)) {
                setStatus("扫描中", true);
                appendLog("scan_started");
            } else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED.equals(action)) {
                setStatus("已发现 " + devices.size() + " 台设备", true);
                appendLog("scan_finished devices=" + devices.size());
                updateDeviceSpinner();
            } else if (BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(action)) {
                BluetoothDevice device = getBluetoothDeviceExtra(intent);
                int state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.ERROR);
                if (device == null || pendingBondDevice == null) {
                    return;
                }
                if (!safeAddress(device).equals(safeAddress(pendingBondDevice))) {
                    return;
                }
                if (state == BluetoothDevice.BOND_BONDED) {
                    setStatus("配对成功 · 连接中", true);
                    appendLog("bonded " + safeAddress(device));
                    bluetoothClient.connect(device);
                    pendingBondDevice = null;
                    addOrUpdateDevice(device, true, Short.MIN_VALUE);
                    updateDeviceSpinner();
                } else if (state == BluetoothDevice.BOND_NONE) {
                    setStatus("配对失败", false);
                    appendLog("bond_failed " + safeAddress(device));
                    pendingBondDevice = null;
                }
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
            bluetoothClient = new BluetoothSppClient(bluetoothAdapter, this);
            buildUi();
            showEmptyResult();
            loadSavedResults();
            renderStoredState();
            registerBluetoothReceiver();
            requestBluetoothPermissionIfNeeded();
            refreshKnownDevices(false);
            showTab(TAB_HOME);
        } catch (Throwable error) {
            Log.e(TAG, "onCreate failed", error);
            Toast.makeText(
                    this,
                    "App 启动失败：" + error.getClass().getSimpleName() + " "
                            + (error.getMessage() == null ? "" : error.getMessage()),
                    Toast.LENGTH_LONG
            ).show();
            throw error;
        }
    }

    private BluetoothDevice getBluetoothDeviceExtra(Intent intent) {
        if (intent == null) {
            return null;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice.class);
        }
        return intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
    }

    @Override
    protected void onDestroy() {
        cancelDiscoveryQuietly();
        if (receiverRegistered) {
            unregisterReceiver(bluetoothReceiver);
            receiverRegistered = false;
        }
        bluetoothClient.shutdown();
        super.onDestroy();
    }

    private void buildUi() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(color(COLOR_PAGE));
            getWindow().setNavigationBarColor(color(COLOR_PAGE));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        }

        LinearLayout appRoot = new LinearLayout(this);
        appRoot.setOrientation(LinearLayout.VERTICAL);
        appRoot.setBackgroundColor(color(COLOR_PAGE));

        FrameLayout contentFrame = new FrameLayout(this);
        appRoot.addView(contentFrame, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        buildHomePage(contentFrame);
        buildAdvicePage(contentFrame);
        buildRecordsPage(contentFrame);
        buildSettingsPage(contentFrame);

        LinearLayout navBar = row();
        navBar.setBackgroundResource(R.drawable.bg_nav_bar);
        navBar.setPadding(dp(6), dp(6), dp(6), dp(6));
        LinearLayout.LayoutParams navParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        navParams.setMargins(dp(10), dp(4), dp(10), dp(10));
        appRoot.addView(navBar, navParams);

        homeNavButton = navButton("主页", R.drawable.ic_home, TAB_HOME);
        adviceNavButton = navButton("康复", R.drawable.ic_advice, TAB_ADVICE);
        recordsNavButton = navButton("记录", R.drawable.ic_records, TAB_RECORDS);
        settingsNavButton = navButton("设置", R.drawable.ic_settings, TAB_SETTINGS);
        navBar.addView(homeNavButton, navWeight());
        navBar.addView(adviceNavButton, navWeight());
        navBar.addView(recordsNavButton, navWeight());
        navBar.addView(settingsNavButton, navWeight());

        setContentView(appRoot);
    }

    private void buildHomePage(FrameLayout contentFrame) {
        LinearLayout root = createPage(contentFrame, TAB_HOME);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setBackgroundResource(R.drawable.bg_header);
        header.setPadding(dp(16), dp(16), dp(16), dp(16));
        root.addView(header, matchWrapBottom(12));

        LinearLayout brandRow = row();
        brandRow.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(brandRow, matchWrapBottom(12));

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_wellness);
        logo.setBackgroundResource(R.drawable.bg_logo_mark);
        logo.setPadding(dp(9), dp(9), dp(9), dp(9));
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(dp(44), dp(44));
        logoParams.setMargins(0, 0, dp(12), 0);
        brandRow.addView(logo, logoParams);

        LinearLayout brandText = new LinearLayout(this);
        brandText.setOrientation(LinearLayout.VERTICAL);
        brandRow.addView(brandText, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        TextView productLabel = text("居家康复管理", 12, COLOR_PRIMARY, Typeface.BOLD);
        brandText.addView(productLabel, matchWrapBottom(2));
        brandText.addView(text("居家康复助手", 26, COLOR_INK, Typeface.BOLD), matchWrap());

        TextView subtitle = text("训练、建议、记录与知识一体化管理。", 14, COLOR_MUTED, Typeface.NORMAL);
        subtitle.setLineSpacing(0, 1.18f);
        header.addView(subtitle, matchWrapBottom(12));

        statusView = text("离线", 13, COLOR_DANGER, Typeface.BOLD);
        statusView.setGravity(Gravity.CENTER_VERTICAL);
        statusView.setBackgroundResource(R.drawable.bg_status_alert);
        statusView.setPadding(dp(12), dp(9), dp(12), dp(9));
        header.addView(statusView, matchWrap());

        LinearLayout quickCard = card();
        root.addView(quickCard, matchWrapBottom(12));
        quickCard.addView(sectionHeader("快捷入口", ""), matchWrapBottom(12));

        LinearLayout quickRowOne = row();
        quickCard.addView(quickRowOne, matchWrapBottom(8));
        quickRowOne.addView(quickActionTile("设备", R.drawable.ic_bluetooth, true, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showTab(TAB_SETTINGS);
                startBluetoothScan();
            }
        }), tileWeight());
        quickRowOne.addView(quickActionTile("同步", R.drawable.ic_download, false, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendCommand("request_latest");
            }
        }), tileWeight());

        LinearLayout quickRowTwo = row();
        quickCard.addView(quickRowTwo, matchWrap());
        quickRowTwo.addView(quickActionTile("康复", R.drawable.ic_advice, false, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showTab(TAB_ADVICE);
            }
        }), tileWeight());
        quickRowTwo.addView(quickActionTile("记录", R.drawable.ic_records, false, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showTab(TAB_RECORDS);
            }
        }), tileWeight());

        LinearLayout scoreCard = card();
        root.addView(scoreCard, matchWrapBottom(12));
        scoreCard.addView(sectionHeader("今日康复", ""), matchWrapBottom(12));

        LinearLayout scorePanel = new LinearLayout(this);
        scorePanel.setOrientation(LinearLayout.HORIZONTAL);
        scorePanel.setGravity(Gravity.CENTER_VERTICAL);
        scorePanel.setBackgroundResource(R.drawable.bg_score);
        scorePanel.setPadding(dp(14), dp(14), dp(14), dp(14));
        scoreCard.addView(scorePanel, matchWrapBottom(10));

        LinearLayout scoreStack = new LinearLayout(this);
        scoreStack.setOrientation(LinearLayout.VERTICAL);
        scoreStack.setGravity(Gravity.CENTER);
        scorePanel.addView(scoreStack, new LinearLayout.LayoutParams(dp(112), LinearLayout.LayoutParams.WRAP_CONTENT));

        scoreView = text("--", 44, COLOR_PRIMARY_DARK, Typeface.BOLD);
        scoreView.setGravity(Gravity.CENTER);
        scoreView.setIncludeFontPadding(false);
        scoreStack.addView(scoreView, matchWrapBottom(4));

        scoreCaptionView = text("综合得分", 12, COLOR_MUTED, Typeface.BOLD);
        scoreCaptionView.setGravity(Gravity.CENTER);
        scoreStack.addView(scoreCaptionView, matchWrap());

        LinearLayout scoreMeta = new LinearLayout(this);
        scoreMeta.setOrientation(LinearLayout.VERTICAL);
        scoreMeta.setPadding(dp(12), 0, 0, 0);
        scorePanel.addView(scoreMeta, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        levelView = text("未评估", 19, COLOR_INK, Typeface.BOLD);
        scoreMeta.addView(levelView, matchWrapBottom(8));

        sourceView = chipText("来源 --", COLOR_PRIMARY_DARK);
        timeView = chipText("时间 --", COLOR_MUTED);
        scoreMeta.addView(sourceView, matchWrapBottom(6));
        scoreMeta.addView(timeView, matchWrap());

        homeAdvicePreviewView = text("", 14, 0xFF33485C, Typeface.NORMAL);
        homeAdvicePreviewView.setBackgroundResource(R.drawable.bg_advice);
        homeAdvicePreviewView.setPadding(dp(12), dp(12), dp(12), dp(12));
        homeAdvicePreviewView.setLineSpacing(0, 1.2f);
        scoreCard.addView(homeAdvicePreviewView, matchWrap());

        LinearLayout overviewCard = card();
        root.addView(overviewCard, matchWrap());
        overviewCard.addView(sectionHeader("概览", ""), matchWrapBottom(10));

        LinearLayout overviewRow = row();
        overviewCard.addView(overviewRow, matchWrapBottom(10));
        homeDeviceCountView = text("0 台", 18, COLOR_PRIMARY_DARK, Typeface.BOLD);
        homeRecordCountView = text("0 条", 18, COLOR_PRIMARY_DARK, Typeface.BOLD);
        overviewRow.addView(statTile("设备", homeDeviceCountView), tileWeight());
        overviewRow.addView(statTile("记录", homeRecordCountView), tileWeight());

        homeLatestSummaryView = emptyHint("今日暂无记录");
        overviewCard.addView(homeLatestSummaryView, matchWrap());
    }

    private void buildAdvicePage(FrameLayout contentFrame) {
        LinearLayout root = createPage(contentFrame, TAB_ADVICE);
        root.addView(moduleHeader("康复知识", "锻炼建议、康复药物、动作库"), matchWrapBottom(12));

        liveAdviceContainer = new LinearLayout(this);
        liveAdviceContainer.setOrientation(LinearLayout.VERTICAL);
        root.addView(liveAdviceContainer, matchWrapBottom(12));

        LinearLayout adviceCard = card();
        liveAdviceContainer.addView(adviceCard, matchWrapBottom(12));
        adviceCard.addView(sectionHeader("当前建议", ""), matchWrapBottom(10));
        adviceMetaView = chipText("今日", COLOR_MUTED);
        adviceCard.addView(adviceMetaView, matchWrapBottom(8));

        adviceView = text("", 15, 0xFF33485C, Typeface.NORMAL);
        adviceView.setLineSpacing(0, 1.25f);
        adviceView.setPadding(dp(12), dp(12), dp(12), dp(12));
        adviceView.setBackgroundResource(R.drawable.bg_advice);
        adviceCard.addView(adviceView, matchWrap());

        LinearLayout dimsCard = card();
        liveAdviceContainer.addView(dimsCard, matchWrap());
        dimsCard.addView(sectionHeader("六维评估", ""), matchWrapBottom(10));
        dimensionsContainer = new LinearLayout(this);
        dimensionsContainer.setOrientation(LinearLayout.VERTICAL);
        dimsCard.addView(dimensionsContainer, matchWrap());

        LinearLayout assessmentHistoryCard = card();
        liveAdviceContainer.addView(assessmentHistoryCard, matchWrap());
        assessmentHistoryCard.addView(sectionHeader("评估历史", ""), matchWrapBottom(10));
        assessmentHistorySummaryView = chipText("0 条", COLOR_MUTED);
        assessmentHistoryCard.addView(assessmentHistorySummaryView, matchWrapBottom(8));
        assessmentHistoryContainer = new LinearLayout(this);
        assessmentHistoryContainer.setOrientation(LinearLayout.VERTICAL);
        assessmentHistoryCard.addView(assessmentHistoryContainer, matchWrap());

        knowledgeHomeContainer = new LinearLayout(this);
        knowledgeHomeContainer.setOrientation(LinearLayout.VERTICAL);
        root.addView(knowledgeHomeContainer, matchWrapBottom(12));

        LinearLayout knowledgeCard = card();
        knowledgeHomeContainer.addView(knowledgeCard, matchWrap());
        knowledgeCard.addView(sectionHeader("知识中心", ""), matchWrapBottom(12));
        knowledgeCard.addView(knowledgeCategoryCard(
                "康复锻炼建议",
                "肌肉损伤、肌肉拉伤、老年训练、肌无力",
                R.drawable.jfdaily_home_care,
                new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        showKnowledgeCategory("advice");
                    }
                }), matchWrapBottom(10));
        knowledgeCard.addView(knowledgeCategoryCard(
                "常见康复药物",
                "疼痛管理、肌无力用药、帕金森用药与安全提醒",
                R.drawable.minhou_recovery_3,
                new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        showKnowledgeCategory("medicine");
                    }
                }), matchWrapBottom(10));
        knowledgeCard.addView(knowledgeCategoryCard(
                "锻炼动作",
                "上肢、下肢、帕金森训练动作和注意事项",
                R.drawable.pumch_sit_stand,
                new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        showKnowledgeCategory("exercise");
                    }
                }), matchWrap());

        knowledgeDetailContainer = new LinearLayout(this);
        knowledgeDetailContainer.setOrientation(LinearLayout.VERTICAL);
        knowledgeDetailContainer.setVisibility(View.GONE);
        root.addView(knowledgeDetailContainer, matchWrap());

        LinearLayout detailCard = card();
        knowledgeDetailContainer.addView(detailCard, matchWrap());
        Button backButton = secondaryButton("返回分类", R.drawable.ic_refresh, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showKnowledgeHome();
            }
        });
        detailCard.addView(backButton, matchWrapBottom(10));

        knowledgeDetailTitleView = text("康复知识", 22, COLOR_INK, Typeface.BOLD);
        knowledgeDetailTitleView.setIncludeFontPadding(false);
        detailCard.addView(knowledgeDetailTitleView, matchWrapBottom(6));

        knowledgeDetailSubtitleView = text("", 13, COLOR_MUTED, Typeface.NORMAL);
        knowledgeDetailSubtitleView.setLineSpacing(0, 1.18f);
        detailCard.addView(knowledgeDetailSubtitleView, matchWrapBottom(12));

        knowledgeDetailBody = new LinearLayout(this);
        knowledgeDetailBody.setOrientation(LinearLayout.VERTICAL);
        detailCard.addView(knowledgeDetailBody, matchWrap());
    }

    private void buildRecordsPage(FrameLayout contentFrame) {
        LinearLayout root = createPage(contentFrame, TAB_RECORDS);
        root.addView(moduleHeader("训练记录", "最近训练与动作表现"), matchWrapBottom(12));

        LinearLayout summaryCard = card();
        root.addView(summaryCard, matchWrapBottom(12));
        summaryCard.addView(sectionHeader("记录概览", ""), matchWrapBottom(10));
        recordsSummaryView = chipText("0 条", COLOR_MUTED);
        summaryCard.addView(recordsSummaryView, matchWrap());

        LinearLayout actionCard = card();
        root.addView(actionCard, matchWrapBottom(12));
        actionCard.addView(sectionHeader("本次动作", ""), matchWrapBottom(10));
        actionsContainer = new LinearLayout(this);
        actionsContainer.setOrientation(LinearLayout.VERTICAL);
        actionCard.addView(actionsContainer, matchWrap());

        LinearLayout recordsCard = card();
        root.addView(recordsCard, matchWrap());
        recordsCard.addView(sectionHeader("历史列表", ""), matchWrapBottom(10));
        recordsContainer = new LinearLayout(this);
        recordsContainer.setOrientation(LinearLayout.VERTICAL);
        recordsCard.addView(recordsContainer, matchWrap());
    }

    private void buildSettingsPage(FrameLayout contentFrame) {
        LinearLayout root = createPage(contentFrame, TAB_SETTINGS);
        root.addView(moduleHeader("设置", "设备、同步与偏好"), matchWrapBottom(12));

        LinearLayout connectionCard = card();
        root.addView(connectionCard, matchWrapBottom(12));
        connectionCard.addView(sectionHeader("设备连接", ""), matchWrapBottom(12));

        settingsStatusSummaryView = chipText("离线", COLOR_DANGER);
        connectionCard.addView(settingsStatusSummaryView, matchWrapBottom(10));

        LinearLayout deviceTitleRow = row();
        deviceTitleRow.setGravity(Gravity.CENTER_VERTICAL);
        connectionCard.addView(deviceTitleRow, matchWrapBottom(8));

        TextView deviceLabel = text("设备", 14, COLOR_INK, Typeface.BOLD);
        deviceTitleRow.addView(deviceLabel, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        deviceCountView = chipText("0 台", COLOR_MUTED);
        deviceTitleRow.addView(deviceCountView, wrapWrap());

        deviceSpinner = new Spinner(this);
        deviceSpinner.setBackgroundResource(R.drawable.bg_input);
        deviceSpinner.setPadding(dp(8), 0, dp(8), 0);
        deviceSpinner.setMinimumHeight(dp(48));
        connectionCard.addView(deviceSpinner, matchWrapBottom(8));
        deviceSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                updateConnectionHelp();
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
                updateConnectionHelp();
            }
        });

        connectionHelpView = text("附近设备", 12, COLOR_MUTED, Typeface.NORMAL);
        connectionHelpView.setLineSpacing(0, 1.2f);
        connectionCard.addView(connectionHelpView, matchWrapBottom(12));

        LinearLayout rowOne = row();
        connectionCard.addView(rowOne, matchWrapBottom(8));
        rowOne.addView(primaryButton("扫描", R.drawable.ic_bluetooth, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startBluetoothScan();
            }
        }), weightWrap(1));
        rowOne.addView(secondaryButton("刷新", R.drawable.ic_refresh, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                refreshKnownDevices(true);
            }
        }), weightWrap(1));

        LinearLayout rowTwo = row();
        connectionCard.addView(rowTwo, matchWrap());
        rowTwo.addView(primaryButton("连接", R.drawable.ic_bluetooth, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                connectSelectedDevice();
            }
        }), weightWrap(1));
        rowTwo.addView(secondaryButton("断开", R.drawable.ic_disconnect, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                bluetoothClient.disconnect("手动断开");
            }
        }), weightWrap(1));

        LinearLayout rowThree = row();
        connectionCard.addView(rowThree, matchWrapBottom(0));
        rowThree.addView(secondaryButton("同步", R.drawable.ic_download, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendCommand("request_latest");
            }
        }), weightWrap(1));
        rowThree.addView(secondaryButton("状态", R.drawable.ic_refresh, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendCommand("request_status");
            }
        }), weightWrap(1));

        LinearLayout preferenceCard = card();
        root.addView(preferenceCard, matchWrapBottom(12));
        preferenceCard.addView(sectionHeader("应用设置", ""), matchWrapBottom(10));

        autoFetchCheck = settingCheck("自动同步", "连接成功后自动更新训练结果。", true);
        preferenceCard.addView(autoFetchCheck, matchWrapBottom(8));

        settingsPermissionView = emptyHint("附近设备权限");
        preferenceCard.addView(settingsPermissionView, matchWrapBottom(8));

        TextView buildInfoView = text("App 版本 " + APP_BUILD_ID, 12, COLOR_MUTED, Typeface.NORMAL);
        preferenceCard.addView(buildInfoView, matchWrap());
        updatePermissionSummary();
    }

    private View knowledgeCategoryCard(String title, String subtitle, int imageRes, View.OnClickListener listener) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.HORIZONTAL);
        outer.setGravity(Gravity.CENTER_VERTICAL);
        outer.setBackgroundResource(R.drawable.bg_metric_row);
        outer.setPadding(dp(10), dp(10), dp(10), dp(10));
        outer.setClickable(true);
        outer.setOnClickListener(listener);

        ImageView image = new ImageView(this);
        image.setImageResource(safeDrawable(imageRes));
        image.setAdjustViewBounds(true);
        image.setBackgroundResource(R.drawable.bg_chip);
        image.setPadding(dp(4), dp(4), dp(4), dp(4));
        image.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams imageParams = new LinearLayout.LayoutParams(dp(116), dp(76));
        imageParams.setMargins(0, 0, dp(12), 0);
        outer.addView(image, imageParams);

        LinearLayout copy = new LinearLayout(this);
        copy.setOrientation(LinearLayout.VERTICAL);
        outer.addView(copy, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        copy.addView(text(title, 16, COLOR_INK, Typeface.BOLD), matchWrapBottom(4));
        TextView subtitleView = text(subtitle, 12, COLOR_MUTED, Typeface.NORMAL);
        subtitleView.setLineSpacing(0, 1.18f);
        copy.addView(subtitleView, matchWrapBottom(6));
        copy.addView(chipText("查看详情", COLOR_PRIMARY_DARK), wrapWrap());
        return outer;
    }

    private void showKnowledgeHome() {
        liveAdviceContainer.setVisibility(View.VISIBLE);
        knowledgeHomeContainer.setVisibility(View.VISIBLE);
        knowledgeDetailContainer.setVisibility(View.GONE);
    }

    private void showKnowledgeCategory(String category) {
        liveAdviceContainer.setVisibility(View.GONE);
        knowledgeHomeContainer.setVisibility(View.GONE);
        knowledgeDetailContainer.setVisibility(View.VISIBLE);
        knowledgeDetailBody.removeAllViews();
        if ("medicine".equals(category)) {
            renderMedicineKnowledge();
        } else if ("exercise".equals(category)) {
            renderExerciseKnowledge();
        } else {
            renderAdviceKnowledge();
        }
    }

    private void renderAdviceKnowledge() {
        knowledgeDetailTitleView.setText("康复锻炼建议");
        knowledgeDetailSubtitleView.setText("覆盖肌肉损伤、肌肉拉伤、老年训练、肌无力和帕金森康复。训练以安全、循序渐进和可坚持为核心。");
        knowledgeDetailBody.addView(detailBlock(
                "肌肉损伤或拉伤",
                "早期以保护受伤部位、休息、冷敷、适度加压和抬高为主。前 2-3 天避免热敷、饮酒和按摩；疼痛允许后再逐步恢复轻柔活动，避免关节或肌肉僵硬。\n\n若听到断裂声、局部变形、皮肤发青发冷、突然麻木刺痛、肿胀明显加重或几天后仍无改善，应尽快就医评估。",
                R.drawable.minhou_recovery_2,
                "参考：NHS、MedlinePlus、AAOS"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌肉拉伤恢复分期",
                "急性期以减轻疼痛和肿胀为主，不做强拉伸。疼痛下降后进入恢复期，可从主动活动、等长收缩和轻阻力练习开始。回归训练前，应能完成日常动作且疼痛不明显。\n\n若运动后疼痛持续到第二天、局部再次肿胀或力量明显下降，应降低训练量。",
                R.drawable.minhou_recovery_2,
                "拉伤恢复"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "老年人日常锻炼",
                "建议把耐力、力量、平衡和柔韧性组合起来。可从步行、坐站训练、扶椅提踵、弹力带划船、靠墙俯卧撑、单脚站立辅助练习开始。\n\n每周保持规律训练，比一次训练很长更重要。训练前后关注血压、头晕、胸闷、关节痛和跌倒风险。",
                R.drawable.pumch_sit_stand,
                "参考：NIA 老年运动建议"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌无力与疲劳管理",
                "肌无力人群应避免一次性高强度训练，建议采用短时、多次、间歇式练习。优先训练坐站转换、核心稳定、轻阻力上肢和下肢动作，并把较难动作放在精力较好的时段。\n\n若存在重症肌无力、吞咽困难、呼吸费力或眼睑下垂加重，应先由神经内科医生评估，再由治疗师制定运动计划。",
                R.drawable.pumch_upper_limb,
                "参考：MedlinePlus 肌无力资料"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "帕金森康复",
                "帕金森目前不能根治，但药物、物理治疗、作业治疗、言语吞咽训练和规律运动可以帮助维持生活质量。训练重点包括步态、平衡、柔韧性、姿势、协调和耐力。\n\n建议与神经内科医生、康复治疗师共同制定计划；运动强度以安全、可坚持、不诱发跌倒为前提。",
                R.drawable.baidu_parkinson_2,
                "参考：NHS、Parkinson's Foundation"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "上肢与下肢训练安排",
                "上肢训练可重点关注肩关节活动度、肩胛稳定、肘腕手精细动作和抓握能力。下肢训练可重点关注髋膝踝力量、步态、平衡、坐站转换和耐力。\n\n每次训练先做 5-10 分钟低强度热身，动作范围以无明显疼痛为准，逐渐增加次数和阻力。",
                R.drawable.pumch_lower_limb,
                "参考：AAOS 肩/膝康复训练原则"), matchWrap());
    }

    private void renderMedicineKnowledge() {
        knowledgeDetailTitleView.setText("常见康复药物");
        knowledgeDetailSubtitleView.setText("只提供常见类别和安全提醒，不提供剂量。具体药物、剂量和停换药必须由医生或药师确认。");
        knowledgeDetailBody.addView(detailBlock(
                "肌肉损伤疼痛管理",
                "常见选择包括对乙酰氨基酚用于缓解疼痛，布洛芬凝胶、喷雾或其他外用 NSAIDs 用于局部疼痛和肿胀；必要时医生或药师可能建议口服布洛芬、萘普生等 NSAIDs。\n\n有胃溃疡、肾病、心血管病、高血压、正在使用抗凝药、孕期或老年人，用药前应先咨询医生或药师。",
                R.drawable.minhou_recovery_3,
                "参考：NHS、MedlinePlus、AAOS"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌肉拉伤恢复用药",
                "轻中度拉伤通常以短期止痛和局部消炎为主，可在医生或药师指导下选择外用 NSAIDs、止痛贴膏或口服止痛药。药物只能帮助控制疼痛，不能替代休息、分期训练和力量恢复。\n\n如果疼痛需要长期用药、夜间痛明显或活动范围持续下降，应复查是否存在撕裂、神经受压或其他问题。",
                R.drawable.minhou_recovery_2,
                "拉伤用药"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "老年人用药注意",
                "老年人常合并高血压、糖尿病、胃病、肾功能下降或多种药物联用。止痛药、抗炎药、肌肉松弛药和镇静类药物都需要谨慎，避免跌倒、胃肠出血、肾功能负担或嗜睡。\n\n建议优先由医生或药师核对现有用药，再决定是否使用新的止痛或康复相关药物。",
                R.drawable.jfdaily_home_care2,
                "老年用药安全"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌无力相关药物",
                "确诊重症肌无力时，常见治疗类别包括吡啶斯的明等胆碱酯酶抑制剂，以及泼尼松、硫唑嘌呤、吗替麦考酚酯等免疫调节药物；急性加重时可能需要 IVIg、血浆置换等医院治疗。\n\n部分药物可能加重肌无力症状，用药前应告知医生已有诊断和当前药物。",
                R.drawable.pumch_upper_limb,
                "参考：MedlinePlus、NHS"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "帕金森常见药物类别",
                "常见类别包括左旋多巴制剂，通常与卡比多巴或苄丝肼联合；多巴胺受体激动剂，如普拉克索、罗匹尼罗、罗替戈汀贴片；MAO-B 抑制剂，如司来吉兰、雷沙吉兰；中晚期还可能使用 COMT 抑制剂。\n\n这些药物可能带来恶心、头晕、嗜睡、幻觉、异动症或冲动控制问题，需由专科医生定期复查。",
                R.drawable.baidu_parkinson_1,
                "参考：NHS 帕金森治疗资料"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "对乙酰氨基酚与复方感冒药",
                "对乙酰氨基酚常用于轻中度疼痛和发热，也常藏在复方感冒药、止咳药或夜间用药中。重复使用多个含同一成分的药物，可能在不知不觉中增加肝脏风险。\n\n正在饮酒、已有肝病、同时使用多种止痛药或不确定药品成分时，应先让医生或药师核对标签。孕期、儿童和老年人更应按医嘱或说明书使用。",
                R.drawable.minhou_recovery_1,
                "参考：MedlinePlus 对乙酰氨基酚"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "NSAIDs 与心胃肾风险",
                "布洛芬、萘普生、阿司匹林和部分处方抗炎药都属于常见抗炎止痛相关药物。它们可缓解疼痛和炎症，但也可能增加胃肠出血、血压升高、肾功能负担或心血管事件风险。\n\n有胃溃疡、肾病、心血管病、高血压、正在服用抗凝药或年龄较大的人，不建议自行长期使用。若出现黑便、呕血、胸痛、气短、单侧无力等情况，应及时就医。",
                R.drawable.minhou_recovery_4,
                "参考：MedlinePlus 布洛芬"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "外用止痛药与贴膏",
                "外用凝胶、喷雾、贴膏可用于局部肌肉或关节疼痛，通常全身暴露较少，但仍可能引起皮肤刺激、过敏或与同类口服药叠加。\n\n不要贴在破损皮肤、感染部位或大面积皮肤上；不要同时热敷、电热毯加热或长时间覆盖。若皮疹、灼痛、瘙痒明显，应停止使用并咨询医生或药师。",
                R.drawable.minhou_recovery_5,
                "局部用药安全"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌肉松弛药与痉挛管理",
                "巴氯芬、替扎尼定、环苯扎林等药物可能用于痉挛或肌肉紧张相关问题，但常见不适包括困倦、头晕、无力、口干或反应变慢。老年人使用后跌倒风险可能增加。\n\n这类药物不应和酒精、镇静催眠药随意叠加；开车、洗澡、上下楼前要格外谨慎。巴氯芬等药物不可突然自行停用，停换药需要医生逐步安排。",
                R.drawable.pumch_core,
                "参考：MedlinePlus 巴氯芬"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "骨质疏松与跌倒预防",
                "康复训练中如果存在骨质疏松、既往骨折或长期卧床，应关注钙、维生素 D、负重训练、平衡训练和防跌倒环境。部分人可能需要双膦酸盐、地舒单抗等抗骨质疏松药物，由医生根据骨密度和骨折风险判断。\n\n训练时避免突然扭转、过度弯腰搬重物和高风险跳跃。出现身高变矮、背痛、轻微外伤后疼痛明显，应评估是否有压缩性骨折。",
                R.drawable.pumch_lower_limb,
                "参考：NIAMS 骨质疏松"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "家庭用药清单",
                "建议把处方药、非处方药、外用药、保健品、草药和过敏史记录在同一张清单中，写清药名、用途、服用时间和开药医生。就诊、买药或住院时带上这张清单，可帮助医生判断相互作用和重复用药。\n\n若出现新发头晕、嗜睡、意识混乱、跌倒、食欲明显下降或尿量变化，要回想近期是否新增或调整过药物，并尽快咨询专业人员。",
                R.drawable.jfdaily_home_care2,
                "用药核对"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "用药安全提醒",
                "不要自行增减、停用或混合药物。若出现突然嗜睡、意识混乱、幻觉、严重头晕、黑便、呼吸困难、皮疹或疼痛迅速加重，应及时联系医生。\n\nApp 内药物信息用于了解方向，不能替代处方、药师审方或线下诊疗。",
                R.drawable.jfdaily_home_care,
                "安全提示"), matchWrap());
    }

    private void renderExerciseKnowledge() {
        knowledgeDetailTitleView.setText("锻炼动作");
        knowledgeDetailSubtitleView.setText("动作以低风险、居家可做为主。训练过程中若出现明显疼痛、胸闷、头晕、跌倒风险或症状加重，应立即停止。");
        knowledgeDetailBody.addView(detailBlock(
                "肌肉损伤早期动作",
                "1. 关节轻柔活动：在无明显疼痛范围内做小幅屈伸。\n2. 等长收缩：肌肉轻轻用力但关节不移动，保持 3-5 秒。\n3. 呼吸放松：配合腹式呼吸，减少紧张和保护性僵硬。\n4. 低负荷步行：下肢轻伤且可负重时，从短距离慢走开始。",
                R.drawable.minhou_recovery_2,
                "损伤早期"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌肉拉伤恢复动作",
                "1. 主动活动：疼痛下降后做完整但轻柔的关节活动。\n2. 弹力带轻阻力：从最小阻力开始，动作慢而可控。\n3. 离心控制：恢复后期逐步加入慢放动作，例如慢慢放下脚跟或手臂。\n4. 功能动作：最后回到上下楼、坐站、提物等日常场景。",
                R.drawable.pumch_core,
                "拉伤恢复"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "上肢动作",
                "1. 钟摆运动：一手扶桌，另一侧手臂自然下垂，前后、左右、小范围画圈摆动。\n2. 交叉抱臂拉伸：放松肩部，将手臂轻轻横过胸前，不要压迫肘关节。\n3. 弹力带划船/外旋：肘部靠近身体，慢慢向后拉或向外旋，感受肩胛稳定。\n4. 肩胛收缩：肩胛骨轻轻向后向下夹紧，保持数秒后放松。",
                R.drawable.pumch_upper_limb,
                "参考：AAOS 肩袖与肩部训练"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "下肢动作",
                "1. 跟腱和小腿拉伸：面对墙，一脚在后，脚跟贴地，身体向前。\n2. 股四头肌拉伸：扶墙站稳，屈膝将脚跟靠近臀部。\n3. 腘绳肌拉伸：仰卧抬腿，用毛巾辅助牵拉。\n4. 半蹲、直腿抬高、提踵：从少量开始，必要时扶椅保持平衡。",
                R.drawable.pumch_lower_limb,
                "参考：AAOS 膝关节训练"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "老年人基础动作",
                "1. 坐站训练：从椅子坐起再慢慢坐下，必要时扶椅背。\n2. 扶椅提踵：双手扶椅，脚跟抬起再缓慢落下。\n3. 靠墙俯卧撑：站立面对墙，双手推墙练习上肢力量。\n4. 平衡转移：扶稳后左右转移重心，逐步练习单脚轻抬。",
                R.drawable.pumch_sit_stand,
                "老年训练"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "肌无力低疲劳训练",
                "1. 分段练习：每组时间短，组间休息充分。\n2. 呼吸肌与姿势：练习坐姿挺胸、缩下巴、缓慢深呼吸。\n3. 轻阻力训练：弹力带或水瓶从低强度开始，避免做到力竭。\n4. 日常功能训练：优先练习翻身、坐站、步行和安全转移。",
                R.drawable.pumch_upper_limb,
                "肌无力训练"), matchWrapBottom(10));
        knowledgeDetailBody.addView(detailBlock(
                "帕金森运动",
                "可选择步行、骑车、太极、瑜伽、舞蹈、力量训练、非接触式拳击和平衡训练。建议把有氧、力量和拉伸组合起来，每周逐步累积规律运动时间。\n\n音乐节拍、口令提示、较大幅度的功能动作有助于步态和动作启动；进阶训练最好在治疗师指导下进行。",
                R.drawable.baidu_parkinson_2,
                "参考：Parkinson's Foundation"), matchWrap());
    }

    private View detailBlock(String title, String body, int imageRes, String source) {
        LinearLayout block = new LinearLayout(this);
        block.setOrientation(LinearLayout.VERTICAL);
        block.setBackgroundResource(R.drawable.bg_metric_row);
        block.setPadding(dp(10), dp(10), dp(10), dp(10));

        ImageView image = new ImageView(this);
        image.setImageResource(safeDrawable(imageRes));
        image.setAdjustViewBounds(true);
        image.setScaleType(ImageView.ScaleType.FIT_CENTER);
        image.setBackgroundResource(R.drawable.bg_chip);
        image.setPadding(dp(4), dp(4), dp(4), dp(4));
        block.addView(image, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(158)));

        TextView titleView = text(title, 16, COLOR_INK, Typeface.BOLD);
        titleView.setPadding(0, dp(10), 0, 0);
        block.addView(titleView, matchWrapBottom(6));

        TextView bodyView = text(body, 13, COLOR_MUTED, Typeface.NORMAL);
        bodyView.setLineSpacing(0, 1.2f);
        block.addView(bodyView, matchWrapBottom(8));

        block.addView(chipText(source, COLOR_PRIMARY_DARK), wrapWrap());
        return block;
    }

    private LinearLayout createPage(FrameLayout contentFrame, int tabIndex) {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(color(COLOR_PAGE));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(14), dp(16), dp(18));
        scrollView.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        contentFrame.addView(scrollView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        tabPages[tabIndex] = scrollView;
        return root;
    }

    private LinearLayout moduleHeader(String title, String subtitle) {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setBackgroundResource(R.drawable.bg_header);
        header.setPadding(dp(16), dp(16), dp(16), dp(16));

        TextView module = text("居家康复助手", 12, COLOR_PRIMARY, Typeface.BOLD);
        header.addView(module, matchWrapBottom(4));

        TextView titleView = text(title, 24, COLOR_INK, Typeface.BOLD);
        titleView.setIncludeFontPadding(false);
        header.addView(titleView, matchWrapBottom(8));

        TextView subtitleView = text(subtitle, 14, COLOR_MUTED, Typeface.NORMAL);
        subtitleView.setLineSpacing(0, 1.18f);
        header.addView(subtitleView, matchWrap());
        return header;
    }

    private void showTab(int tab) {
        activeTab = tab;
        for (int i = 0; i < tabPages.length; i++) {
            if (tabPages[i] != null) {
                tabPages[i].setVisibility(i == tab ? View.VISIBLE : View.GONE);
            }
        }
        updateNavButton(homeNavButton, tab == TAB_HOME);
        updateNavButton(adviceNavButton, tab == TAB_ADVICE);
        updateNavButton(recordsNavButton, tab == TAB_RECORDS);
        updateNavButton(settingsNavButton, tab == TAB_SETTINGS);
        if (tab == TAB_SETTINGS) {
            refreshKnownDevices(false);
            startBluetoothScan();
        }
    }

    private void updateNavButton(Button button, boolean selected) {
        if (button == null) {
            return;
        }
        button.setTextColor(color(selected ? COLOR_PRIMARY_DARK : COLOR_MUTED));
        button.setTypeface(Typeface.DEFAULT, selected ? Typeface.BOLD : Typeface.NORMAL);
        button.setBackgroundResource(selected ? R.drawable.bg_nav_selected : R.drawable.bg_nav_item);
    }

    private void registerBluetoothReceiver() {
        if (receiverRegistered) {
            return;
        }
        IntentFilter filter = new IntentFilter();
        filter.addAction(BluetoothDevice.ACTION_FOUND);
        filter.addAction(BluetoothAdapter.ACTION_DISCOVERY_STARTED);
        filter.addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED);
        filter.addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(bluetoothReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(bluetoothReceiver, filter);
        }
        receiverRegistered = true;
    }

    private void showEmptyResult() {
        scoreView.setText("--");
        scoreCaptionView.setText("综合得分");
        levelView.setText("未评估");
        sourceView.setText("来源 --");
        timeView.setText("时间 --");
        homeAdvicePreviewView.setText("今日建议");
        homeLatestSummaryView.setText("今日暂无记录");
        adviceMetaView.setText("今日");
        adviceView.setText("今日建议");
        dimensionsContainer.removeAllViews();
        dimensionsContainer.addView(emptyHint("暂无评估"), matchWrap());
        actionsContainer.removeAllViews();
        actionsContainer.addView(emptyHint("暂无动作"), matchWrap());
        renderTrainingRecords();
        renderAssessmentRecords();
    }

    private void refreshKnownDevices(boolean keepDiscovered) {
        if (bluetoothAdapter == null) {
            setStatus("此手机不支持蓝牙", false);
            return;
        }
        if (!hasBluetoothPermission()) {
            requestBluetoothPermissionIfNeeded();
            return;
        }
        if (!keepDiscovered) {
            devices.clear();
            devicesByAddress.clear();
        }
        try {
            Set<BluetoothDevice> bonded = bluetoothAdapter.getBondedDevices();
            if (bonded != null) {
                for (BluetoothDevice device : bonded) {
                    addOrUpdateDevice(device, true, Short.MIN_VALUE);
                }
            }
            updateDeviceSpinner();
            appendLog("bonded_devices_loaded count=" + devices.size());
        } catch (SecurityException error) {
            setStatus("缺少蓝牙权限", false);
        }
    }

    private void startBluetoothScan() {
        if (bluetoothAdapter == null) {
            setStatus("此手机不支持蓝牙", false);
            return;
        }
        if (!hasBluetoothPermission()) {
            requestBluetoothPermissionIfNeeded();
            return;
        }
        if (!bluetoothAdapter.isEnabled()) {
            Toast.makeText(this, "蓝牙未开启", Toast.LENGTH_LONG).show();
            setStatus("蓝牙未开启", false);
            return;
        }

        try {
            refreshKnownDevices(true);
            if (bluetoothAdapter.isDiscovering()) {
                bluetoothAdapter.cancelDiscovery();
            }
            boolean started = bluetoothAdapter.startDiscovery();
            if (!started) {
                setStatus("扫描失败", false);
            }
        } catch (SecurityException error) {
            setStatus("权限不足", false);
            requestBluetoothPermissionIfNeeded();
        }
    }

    private void connectSelectedDevice() {
        if (!hasBluetoothPermission()) {
            requestBluetoothPermissionIfNeeded();
            return;
        }
        int index = deviceSpinner.getSelectedItemPosition();
        if (index < 0 || index >= devices.size()) {
            Toast.makeText(this, "请选择设备", Toast.LENGTH_LONG).show();
            return;
        }
        BluetoothDevice device = devices.get(index).device;
        cancelDiscoveryQuietly();
        try {
            int bondState = device.getBondState();
            if (bondState == BluetoothDevice.BOND_BONDED) {
                bluetoothClient.connect(device);
            } else if (bondState == BluetoothDevice.BOND_BONDING) {
                pendingBondDevice = device;
                setStatus("配对中", true);
            } else {
                pendingBondDevice = device;
                boolean bondingStarted = device.createBond();
                if (bondingStarted) {
                    setStatus("等待配对确认", true);
                    appendLog("bond_start " + safeAddress(device));
                } else {
                    setStatus("直接连接中", true);
                    bluetoothClient.connect(device);
                }
            }
        } catch (SecurityException error) {
            setStatus("权限不足", false);
            requestBluetoothPermissionIfNeeded();
        }
    }

    private void addOrUpdateDevice(BluetoothDevice device, boolean bonded, short rssi) {
        String address = safeAddress(device);
        if (TextUtils.isEmpty(address)) {
            return;
        }
        DeviceItem existing = devicesByAddress.get(address);
        if (existing == null) {
            existing = new DeviceItem(device);
            devicesByAddress.put(address, existing);
            devices.add(existing);
        }
        existing.bonded = existing.bonded || bonded || safeBondState(device) == BluetoothDevice.BOND_BONDED;
        existing.rssi = rssi;
    }

    private void updateDeviceSpinner() {
        List<String> labels = new ArrayList<>();
        for (DeviceItem item : devices) {
            labels.add(item.toString());
        }
        if (labels.isEmpty()) {
            labels.add("未发现设备");
        }
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        deviceSpinner.setAdapter(adapter);

        String count = devices.size() + " 台";
        deviceCountView.setText(count);
        homeDeviceCountView.setText(devices.size() + " 台");
        updateConnectionHelp();
    }

    private void updateConnectionHelp() {
        int index = deviceSpinner == null ? -1 : deviceSpinner.getSelectedItemPosition();
        if (devices.isEmpty() || index < 0 || index >= devices.size()) {
            connectionHelpView.setText("附近设备");
            return;
        }
        DeviceItem item = devices.get(index);
        String state = item.bonded ? "已配对" : "待配对";
        connectionHelpView.setText(safeDeviceName(item.device) + " · " + state);
    }

    private void cancelDiscoveryQuietly() {
        if (bluetoothAdapter == null) {
            return;
        }
        try {
            if (bluetoothAdapter.isDiscovering()) {
                bluetoothAdapter.cancelDiscovery();
            }
        } catch (SecurityException ignored) {
        }
    }

    private void sendCommand(String command) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("command", command);
            JSONObject message = new JSONObject();
            message.put("type", "command");
            message.put("timestamp", System.currentTimeMillis() / 1000.0);
            message.put("payload", payload);
            bluetoothClient.sendLine(message.toString());
            appendLog("send " + command);
        } catch (Exception error) {
            appendLog("send_error " + error.getMessage());
        }
    }

    private void updateResult(RehabResult result) {
        if (result == null) {
            return;
        }
        upsertResult(result);
        saveSavedResults();
        renderStoredState();
    }

    private void updateResults(List<RehabResult> results) {
        if (results == null || results.isEmpty()) {
            return;
        }
        for (RehabResult result : results) {
            upsertResult(result);
        }
        saveSavedResults();
        renderStoredState();
    }

    private void renderLatestResult(RehabResult result) {
        if (result == null) {
            return;
        }
        latestResult = result;

        if (result.hasScore()) {
            scoreView.setText(String.format(Locale.CHINA, "%.1f", result.totalScore));
            scoreCaptionView.setText("满分 100");
            levelView.setText(result.displayLevel());
            sourceView.setText("来源：" + result.displaySource());
            timeView.setText("时间：" + (TextUtils.isEmpty(result.timestampText) ? nowText() : result.timestampText));
        }

        String advice = TextUtils.isEmpty(result.advice) ? RehabResult.autoAdvice(result.totalScore) : result.advice;
        homeAdvicePreviewView.setText("建议摘要：" + compactText(advice, 72));
        adviceMetaView.setText("来源：" + result.displaySource() + " · " + (TextUtils.isEmpty(result.timestampText) ? nowText() : result.timestampText));
        adviceView.setText("医疗建议：" + advice);
        homeLatestSummaryView.setText(latestSummary(result));

        dimensionsContainer.removeAllViews();
        if (result.dimensionScores.isEmpty()) {
            dimensionsContainer.addView(emptyHint("暂无评估"), matchWrap());
        } else {
            for (Map.Entry<String, Double> entry : result.dimensionsInDisplayOrder().entrySet()) {
                dimensionsContainer.addView(dimensionRow(entry.getKey(), entry.getValue()), matchWrapBottom(8));
            }
        }

        actionsContainer.removeAllViews();
        if (result.actionScores.isEmpty()) {
            actionsContainer.addView(emptyHint("暂无动作"), matchWrap());
        } else {
            for (int i = 0; i < result.actionScores.size(); i++) {
                String name = i < result.actionNames.size() ? result.actionNames.get(i) : "动作 " + (i + 1);
                actionsContainer.addView(actionRow(name, result.actionScores.get(i)), matchWrapBottom(8));
            }
        }
    }

    private void renderStoredState() {
        if (latestResult == null) {
            latestResult = assessmentRecords.isEmpty()
                    ? (trainingRecords.isEmpty() ? null : trainingRecords.get(0))
                    : assessmentRecords.get(0);
        }
        if (latestResult != null) {
            renderLatestResult(latestResult);
        }
        renderTrainingRecords();
        renderAssessmentRecords();
    }

    private void upsertResult(RehabResult result) {
        if (!result.hasScore() && TextUtils.isEmpty(result.advice)) {
            return;
        }
        if (TextUtils.isEmpty(result.timestampText)) {
            result.timestampText = nowText();
        }
        if (TextUtils.isEmpty(result.recordType)) {
            result.recordType = result.isTrainingRecord() ? "training" : "assessment";
        }
        if (TextUtils.isEmpty(result.source)) {
            result.source = result.isTrainingRecord() ? "training" : "assessment";
        }
        if (result.isTrainingRecord()) {
            upsertInto(trainingRecords, result);
        } else {
            result.recordType = "assessment";
            upsertInto(assessmentRecords, result);
        }
        latestResult = result;
    }

    private void upsertInto(List<RehabResult> records, RehabResult result) {
        String key = result.identityKey();
        for (int i = 0; i < records.size(); i++) {
            if (key.equals(records.get(i).identityKey())) {
                records.set(i, result);
                if (i != 0) {
                    records.remove(i);
                    records.add(0, result);
                }
                return;
            }
        }
        records.add(0, result);
        while (records.size() > MAX_SAVED_RECORDS) {
            records.remove(records.size() - 1);
        }
    }

    private void renderTrainingRecords() {
        homeRecordCountView.setText(trainingRecords.size() + " 条");
        recordsSummaryView.setText(trainingRecords.isEmpty()
                ? "0 条"
                : trainingRecords.size() + " 条");
        recordsContainer.removeAllViews();
        if (trainingRecords.isEmpty()) {
            recordsContainer.addView(emptyHint("今日暂无记录"), matchWrap());
            return;
        }
        int count = Math.min(trainingRecords.size(), 12);
        for (int i = 0; i < count; i++) {
            recordsContainer.addView(recordRow(i + 1, trainingRecords.get(i)), matchWrapBottom(8));
        }
    }

    private void renderAssessmentRecords() {
        if (assessmentHistorySummaryView == null || assessmentHistoryContainer == null) {
            return;
        }
        assessmentHistorySummaryView.setText(assessmentRecords.isEmpty()
                ? "0 条"
                : assessmentRecords.size() + " 条");
        assessmentHistoryContainer.removeAllViews();
        if (assessmentRecords.isEmpty()) {
            assessmentHistoryContainer.addView(emptyHint("暂无评估历史"), matchWrap());
            return;
        }
        int count = Math.min(assessmentRecords.size(), 12);
        for (int i = 0; i < count; i++) {
            assessmentHistoryContainer.addView(recordRow(i + 1, assessmentRecords.get(i)), matchWrapBottom(8));
        }
    }

    private void loadSavedResults() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        try {
            readSavedArray(prefs.getString(KEY_TRAINING_RECORDS, "[]"), "training", trainingRecords);
            readSavedArray(prefs.getString(KEY_ASSESSMENT_RECORDS, "[]"), "assessment", assessmentRecords);
        } catch (Exception error) {
            Log.w(TAG, "clear corrupt saved records", error);
            prefs.edit()
                    .remove(KEY_TRAINING_RECORDS)
                    .remove(KEY_ASSESSMENT_RECORDS)
                    .apply();
            trainingRecords.clear();
            assessmentRecords.clear();
        }
        latestResult = assessmentRecords.isEmpty()
                ? (trainingRecords.isEmpty() ? null : trainingRecords.get(0))
                : assessmentRecords.get(0);
    }

    private void saveSavedResults() {
        try {
            SharedPreferences.Editor editor = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit();
            editor.putString(KEY_TRAINING_RECORDS, toSavedArray(trainingRecords).toString());
            editor.putString(KEY_ASSESSMENT_RECORDS, toSavedArray(assessmentRecords).toString());
            editor.apply();
        } catch (Exception error) {
            appendLog("save_records_error " + error.getMessage());
        }
    }

    private void readSavedArray(String json, String defaultType, List<RehabResult> out) {
        out.clear();
        try {
            JSONArray array = new JSONArray(json);
            for (int i = 0; i < array.length(); i++) {
                JSONObject object = array.optJSONObject(i);
                if (object == null) {
                    continue;
                }
                RehabResult result = RehabResult.fromJson(object);
                if (TextUtils.isEmpty(result.recordType)) {
                    result.recordType = defaultType;
                }
                if (TextUtils.isEmpty(result.source)) {
                    result.source = defaultType;
                }
                if (result.hasScore() || !TextUtils.isEmpty(result.advice)) {
                    out.add(result);
                }
            }
        } catch (Exception error) {
            appendLog("load_records_error " + error.getMessage());
        }
    }

    private JSONArray toSavedArray(List<RehabResult> records) throws Exception {
        JSONArray array = new JSONArray();
        for (RehabResult result : records) {
            array.put(result.toJson());
        }
        return array;
    }

    private View recordRow(int index, RehabResult result) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundResource(R.drawable.bg_metric_row);
        outer.setPadding(dp(10), dp(10), dp(10), dp(10));

        LinearLayout top = row();
        top.setGravity(Gravity.CENTER_VERTICAL);
        outer.addView(top, matchWrapBottom(6));

        String title = String.format(Locale.CHINA, "第 %d 条 · %s", index,
                TextUtils.isEmpty(result.timestampText) ? nowText() : result.timestampText);
        top.addView(text(title, 13, COLOR_INK, Typeface.BOLD),
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        String score = result.hasScore() ? String.format(Locale.CHINA, "%.1f 分", result.totalScore) : "建议";
        int recordPercent = Math.max(0, Math.min(100, (int) Math.round(result.totalScore)));
        top.addView(text(score, 13, scoreColor(recordPercent), Typeface.BOLD), wrapWrap());

        TextView meta = text(result.displaySource() + " · " + result.displayLevel(), 12, COLOR_MUTED, Typeface.NORMAL);
        outer.addView(meta, matchWrapBottom(4));

        String advice = TextUtils.isEmpty(result.advice) ? RehabResult.autoAdvice(result.totalScore) : result.advice;
        TextView adviceText = text(compactText(advice, 70), 12, COLOR_MUTED, Typeface.NORMAL);
        adviceText.setLineSpacing(0, 1.15f);
        outer.addView(adviceText, matchWrap());
        return outer;
    }

    private View dimensionRow(String key, double rawValue) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundResource(R.drawable.bg_metric_row);
        outer.setPadding(dp(10), dp(10), dp(10), dp(10));
        int percent = RehabResult.dimensionPercent(key, rawValue);

        LinearLayout top = row();
        top.setGravity(Gravity.CENTER_VERTICAL);
        outer.addView(top, matchWrapBottom(6));

        TextView name = text(RehabResult.dimensionName(key), 14, COLOR_INK, Typeface.BOLD);
        top.addView(name, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        TextView value = text(RehabResult.dimensionValueLabel(key, rawValue), 13, scoreColor(percent), Typeface.BOLD);
        value.setGravity(Gravity.END);
        top.addView(value, wrapWrap());

        ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgress(percent);
        tintProgress(bar, scoreColor(percent));
        outer.addView(bar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(7)));

        TextView suggestion = text(RehabResult.dimensionSuggestion(key, percent),
                12, COLOR_MUTED, Typeface.NORMAL);
        suggestion.setPadding(0, dp(6), 0, 0);
        outer.addView(suggestion, matchWrap());
        return outer;
    }

    private View actionRow(String name, double score) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundResource(R.drawable.bg_metric_row);
        outer.setPadding(dp(10), dp(10), dp(10), dp(10));

        int percent = Math.max(0, Math.min(100, (int) Math.round(score)));

        LinearLayout top = row();
        top.setGravity(Gravity.CENTER_VERTICAL);
        outer.addView(top, matchWrapBottom(6));
        top.addView(text(name, 14, COLOR_INK, Typeface.BOLD),
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        top.addView(text(String.format(Locale.CHINA, "%.1f 分", score), 13, scoreColor(percent), Typeface.BOLD), wrapWrap());

        ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgress(percent);
        tintProgress(bar, scoreColor(percent));
        outer.addView(bar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(7)));
        return outer;
    }

    private void requestBluetoothPermissionIfNeeded() {
        if (hasBluetoothPermission()) {
            updatePermissionSummary();
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            requestPermissions(new String[]{
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.BLUETOOTH_SCAN
            }, REQ_BT_PERMISSION);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, REQ_BT_PERMISSION);
        }
    }

    private boolean hasBluetoothPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        }
        return true;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_BT_PERMISSION) {
            updatePermissionSummary();
            refreshKnownDevices(false);
            startBluetoothScan();
        }
    }

    @Override
    public void onConnecting(final String deviceName) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                setStatus("连接中", true);
            }
        });
    }

    @Override
    public void onConnected(final String deviceName) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                setStatus("在线", true);
                appendLog("connected " + deviceName);
                // 网关 accept 后会主动推送 sync_snapshot，无需立即再 request_sync
            }
        });
    }

    @Override
    public void onDisconnected(final String reason) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                setStatus("蓝牙状态：" + reason, false);
                appendLog("disconnected " + reason);
            }
        });
    }

    @Override
    public void onLineReceived(final String line) {
        RehabMessageParser.ParsedMessage parsed = null;
        String parseError = null;
        try {
            parsed = RehabMessageParser.parse(line);
        } catch (Exception error) {
            parseError = error.getMessage();
        }
        final RehabMessageParser.ParsedMessage finalParsed = parsed;
        final String preview = formatRecvLog(line);
        final String errorMessage = parseError;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                appendLog("recv " + preview);
                if (errorMessage != null) {
                    appendLog("parse_error " + errorMessage);
                    return;
                }
                applyParsedMessage(finalParsed);
            }
        });
    }

    private void applyParsedMessage(RehabMessageParser.ParsedMessage parsed) {
        if (parsed == null) {
            return;
        }
        if (parsed.results != null && !parsed.results.isEmpty()) {
            updateResults(parsed.results);
        } else if (parsed.result != null) {
            updateResult(parsed.result);
        }
        if ("system_status".equals(parsed.rawType) && parsed.status != null) {
            if (parsed.status.contains("ready") || parsed.status.contains("gateway_connected")) {
                setStatus("在线", true);
            } else {
                setStatus("收到状态：" + parsed.rawType, true);
            }
            return;
        }
        if (!TextUtils.isEmpty(parsed.status)) {
            setStatus("收到状态：" + parsed.rawType, true);
        }
    }

    private String formatRecvLog(String line) {
        if (line == null) {
            return "";
        }
        String trimmed = line.trim();
        if (trimmed.length() <= 180) {
            return trimmed;
        }
        return trimmed.substring(0, 180) + "…(" + trimmed.length() + " chars)";
    }

    @Override
    public void onError(final String message, Throwable error) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                setStatus(message, false);
                appendLog("error " + message);
            }
        });
    }

    private void setStatus(String status, boolean ok) {
        if (statusView != null) {
            statusView.setText(status);
            statusView.setTextColor(color(ok ? COLOR_ACCENT : COLOR_DANGER));
            statusView.setBackgroundResource(ok ? R.drawable.bg_status_ok : R.drawable.bg_status_alert);
        }
        if (settingsStatusSummaryView != null) {
            settingsStatusSummaryView.setText(status);
            settingsStatusSummaryView.setTextColor(color(ok ? COLOR_ACCENT : COLOR_DANGER));
        }
    }

    private void appendLog(String line) {
        if (logView == null) {
            return;
        }
        String old = logView.getText().toString();
        String next = "[" + new SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new Date()) + "] " + line;
        if ("无记录".equals(old)) {
            logView.setText(next);
        } else {
            String combined = next + "\n" + old;
            String[] rows = combined.split("\n");
            StringBuilder limited = new StringBuilder();
            for (int i = 0; i < rows.length && i < 30; i++) {
                if (i > 0) {
                    limited.append('\n');
                }
                limited.append(rows[i]);
            }
            logView.setText(limited.toString());
        }
    }

    private void updatePermissionSummary() {
        if (settingsPermissionView == null) {
            return;
        }
        boolean granted = hasBluetoothPermission();
        settingsPermissionView.setText(granted
                ? "附近设备权限 · 已开启"
                : "附近设备权限 · 未开启");
        settingsPermissionView.setTextColor(color(granted ? COLOR_ACCENT : COLOR_DANGER));
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        return card;
    }

    private LinearLayout sectionHeader(String title, String subtitle) {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);

        TextView titleView = text(title, 16, COLOR_INK, Typeface.BOLD);
        titleView.setIncludeFontPadding(false);
        header.addView(titleView, TextUtils.isEmpty(subtitle) ? matchWrap() : matchWrapBottom(4));

        if (!TextUtils.isEmpty(subtitle)) {
            TextView subtitleView = text(subtitle, 12, COLOR_MUTED, Typeface.NORMAL);
            subtitleView.setLineSpacing(0, 1.18f);
            header.addView(subtitleView, matchWrap());
        }
        return header;
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, 0, 0, 0);
        return row;
    }

    private TextView chipText(String value, int textColor) {
        TextView chip = text(value, 12, textColor, Typeface.BOLD);
        chip.setBackgroundResource(R.drawable.bg_chip);
        chip.setPadding(dp(8), dp(5), dp(8), dp(5));
        chip.setGravity(Gravity.CENTER_VERTICAL);
        return chip;
    }

    private TextView emptyHint(String value) {
        TextView hint = text(value, 13, COLOR_MUTED, Typeface.NORMAL);
        hint.setBackgroundResource(R.drawable.bg_metric_row);
        hint.setPadding(dp(10), dp(10), dp(10), dp(10));
        return hint;
    }

    private View quickActionTile(String label, int iconRes, boolean primary, View.OnClickListener listener) {
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(Gravity.CENTER);
        tile.setBackgroundResource(primary ? R.drawable.bg_quick_primary : R.drawable.bg_quick_secondary);
        tile.setPadding(dp(10), dp(14), dp(10), dp(14));
        tile.setMinimumHeight(dp(96));
        tile.setClickable(true);
        tile.setOnClickListener(listener);

        ImageView icon = new ImageView(this);
        icon.setImageResource(iconRes);
        icon.setAdjustViewBounds(true);
        LinearLayout.LayoutParams iconParams = new LinearLayout.LayoutParams(dp(22), dp(22));
        iconParams.setMargins(0, 0, 0, dp(10));
        tile.addView(icon, iconParams);

        TextView labelView = text(label, 13, primary ? 0xFFFFFFFF : COLOR_PRIMARY_DARK, Typeface.BOLD);
        labelView.setGravity(Gravity.CENTER);
        labelView.setIncludeFontPadding(false);
        labelView.setSingleLine(false);
        labelView.setMaxLines(2);
        tile.addView(labelView, matchWrap());
        return tile;
    }

    private View statTile(String label, TextView valueView) {
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(Gravity.CENTER);
        tile.setBackgroundResource(R.drawable.bg_stat_tile);
        tile.setPadding(dp(10), dp(14), dp(10), dp(14));
        tile.setMinimumHeight(dp(84));

        valueView.setGravity(Gravity.CENTER);
        valueView.setIncludeFontPadding(false);
        valueView.setSingleLine(false);
        valueView.setMaxLines(2);
        tile.addView(valueView, matchWrapBottom(8));

        TextView labelView = text(label, 12, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.CENTER);
        labelView.setIncludeFontPadding(false);
        tile.addView(labelView, matchWrap());
        return tile;
    }

    private CheckBox settingCheck(String title, String subtitle, boolean checked) {
        CheckBox checkBox = new CheckBox(this);
        checkBox.setText(TextUtils.isEmpty(subtitle) ? title : title + "\n" + subtitle);
        checkBox.setTextSize(13);
        checkBox.setTextColor(color(COLOR_INK));
        checkBox.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        checkBox.setChecked(checked);
        checkBox.setBackgroundResource(R.drawable.bg_setting_item);
        checkBox.setPadding(dp(10), dp(8), dp(10), dp(8));
        return checkBox;
    }

    private Button primaryButton(String label, int iconRes, View.OnClickListener listener) {
        Button button = baseButton(label, iconRes, listener, false);
        button.setTextColor(color(0xFFFFFFFF));
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setBackgroundResource(R.drawable.bg_primary_button);
        return button;
    }

    private Button secondaryButton(String label, int iconRes, View.OnClickListener listener) {
        Button button = baseButton(label, iconRes, listener, false);
        button.setTextColor(color(COLOR_PRIMARY));
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setBackgroundResource(R.drawable.bg_secondary_button);
        return button;
    }

    private Button navButton(String label, int iconRes, final int tab) {
        Button button = baseButton(label, iconRes, new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showTab(tab);
            }
        }, true);
        button.setBackgroundResource(R.drawable.bg_nav_item);
        button.setTextColor(color(COLOR_MUTED));
        button.setMinHeight(dp(64));
        return button;
    }

    private Button baseButton(String label, int iconRes, View.OnClickListener listener, boolean iconTop) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(iconTop ? 11 : 12);
        button.setSingleLine(false);
        button.setMaxLines(iconTop ? 1 : 2);
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(dp(iconTop ? 64 : 60));
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(dp(8), dp(iconTop ? 6 : 8), dp(8), dp(iconTop ? 6 : 8));
        button.setCompoundDrawablePadding(dp(iconTop ? 4 : 6));
        Drawable icon = getResources().getDrawable(safeDrawable(iconRes), getTheme());
        final int iconSize = dp(iconTop ? 20 : 18);
        icon.setBounds(0, 0, iconSize, iconSize);
        if (iconTop) {
            button.setCompoundDrawables(null, icon, null, null);
        } else {
            button.setCompoundDrawables(icon, null, null, null);
        }
        button.setOnClickListener(listener);
        return button;
    }

    private int safeDrawable(int resId) {
        try {
            if (getResources().getDrawable(resId, getTheme()) != null) {
                return resId;
            }
        } catch (Exception error) {
            Log.w(TAG, "missing drawable resId=" + resId, error);
        }
        return R.drawable.ic_wellness;
    }

    private void tintProgress(ProgressBar bar, int progressColor) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            bar.setProgressTintList(ColorStateList.valueOf(color(progressColor)));
            bar.setProgressBackgroundTintList(ColorStateList.valueOf(color(0xFFE3EBEF)));
        }
    }

    private int scoreColor(int percent) {
        if (percent >= 85) {
            return COLOR_ACCENT;
        }
        if (percent >= 70) {
            return COLOR_PRIMARY;
        }
        if (percent >= 60) {
            return COLOR_WARNING;
        }
        return COLOR_CORAL;
    }

    private String latestSummary(RehabResult result) {
        if (result == null) {
            return "今日暂无记录";
        }
        String score = result.hasScore()
                ? String.format(Locale.CHINA, "%.1f 分", result.totalScore)
                : "未提供得分";
        return "最近一次：" + score + " · " + result.displayLevel() + " · " + result.displaySource();
    }

    private String compactText(String value, int maxChars) {
        if (value == null) {
            return "";
        }
        String normalized = value.replace('\n', ' ').trim();
        if (normalized.length() <= maxChars) {
            return normalized;
        }
        return normalized.substring(0, Math.max(0, maxChars - 1)) + "...";
    }

    private TextView text(String value, int sp, int color, int typefaceStyle) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color(color));
        view.setTypeface(Typeface.DEFAULT, typefaceStyle);
        view.setIncludeFontPadding(true);
        view.setLineSpacing(0, 1.1f);
        return view;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams matchWrapBottom(int bottomDp) {
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(bottomDp));
        return params;
    }

    private LinearLayout.LayoutParams weightWrap(float weight) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.WRAP_CONTENT,
                weight);
        params.setMargins(dp(4), 0, dp(4), dp(8));
        return params;
    }

    private LinearLayout.LayoutParams tileWeight() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.WRAP_CONTENT,
                1f);
        params.setMargins(dp(4), 0, dp(4), dp(8));
        return params;
    }

    private LinearLayout.LayoutParams navWeight() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.WRAP_CONTENT,
                1f);
        params.setMargins(dp(2), 0, dp(2), 0);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int color(int argb) {
        return argb;
    }

    private String nowText() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(new Date());
    }

    private int safeBondState(BluetoothDevice device) {
        try {
            return device.getBondState();
        } catch (SecurityException ignored) {
            return BluetoothDevice.BOND_NONE;
        }
    }

    private static String safeAddress(BluetoothDevice device) {
        if (device == null) {
            return "";
        }
        return device.getAddress();
    }

    private static String safeDeviceName(BluetoothDevice device) {
        try {
            String name = device.getName();
            if (name != null && !name.trim().isEmpty()) {
                return name;
            }
        } catch (SecurityException ignored) {
        }
        return safeAddress(device);
    }

    private static String signalLabel(short rssi) {
        if (rssi == Short.MIN_VALUE) {
            return "信号 --";
        }
        if (rssi >= -55) {
            return "信号强";
        }
        if (rssi >= -75) {
            return "信号中";
        }
        return "信号弱";
    }

    private static class DeviceItem {
        final BluetoothDevice device;
        boolean bonded;
        short rssi = Short.MIN_VALUE;

        DeviceItem(BluetoothDevice device) {
            this.device = device;
        }

        @Override
        public String toString() {
            String state = bonded ? "已配对" : "未配对";
            return safeDeviceName(device) + " · " + state + " · " + signalLabel(rssi) + " · " + safeAddress(device);
        }
    }
}
