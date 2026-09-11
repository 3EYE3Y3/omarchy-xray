import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false
  property bool vision: false
  property bool hud: false
  property int hudPid: 0
  property bool loading: false
  property string errorText: ""
  property string queryText: ""
  property string titleText: "X-RAY"
  property string typeText: "SYSTEM"
  property var activeTarget: []
  property var report: ({})
  property var sectionNames: []
  property string selectedSection: "overview"
  property string fontFamily: Style.font.family

  readonly property string scriptPath: Qt.resolvedUrl("bin/xray").toString().replace(/^file:\/\//, "")
  readonly property color background: Color.menu.background
  readonly property color foreground: Color.menu.text
  readonly property color accent: Color.menu.selectedText
  readonly property color borderColor: Color.menu.border
  readonly property color muted: Color.muted
  readonly property color scrim: Color.menu.scrim

  function parsePayload(payloadJson) {
    try { return JSON.parse(payloadJson || "{}") } catch (error) { return {} }
  }

  function open(payloadJson) {
    var payload = parsePayload(payloadJson)
    var mode = String(payload.mode || "inspect")
    if (mode === "vision") {
      vision = !vision
      hud = false
      opened = vision
      if (vision) refreshVision()
      return
    }
    if (mode === "hud") {
      var requestedPid = payload.target && payload.target.length ? parseInt(payload.target[0], 10) : 0
      hud = !(hud && hudPid === requestedPid)
      hudPid = isFinite(requestedPid) ? requestedPid : 0
      vision = false
      opened = hud
      if (hud) refreshVision()
      return
    }
    vision = false
    hud = false
    opened = true
    activeTarget = Array.isArray(payload.target) ? payload.target : []
    inspect(activeTarget)
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function toggle() {
    if (opened) dismiss()
    else open("{}")
  }

  function close() {
    opened = false
    vision = false
    hud = false
  }

  function dismiss() {
    opened = false
    if (!vision && !hud && shell && typeof shell.hide === "function")
      shell.hide((manifest && manifest.id) || "io.github.3eye3y3.xray")
  }

  function inspect(target) {
    if (dataProcess.running) dataProcess.signal(15)
    loading = true
    errorText = ""
    activeTarget = target || []
    dataProcess.command = ["python3", scriptPath, "--json"].concat(activeTarget)
    dataProcess.running = true
  }

  function inspectQuery() {
    var text = String(queryText || "").trim()
    inspect(text ? [text] : [])
  }

  function loadReport(raw) {
    try {
      var parsed = JSON.parse(raw)
      if (parsed.error) {
        errorText = parsed.error
        report = ({})
        detailModel.clear()
        return
      }
      report = parsed
      var target = parsed.target || {}
      titleText = String(target.display_name || "X-RAY")
      typeText = String(target.type || "unknown").toUpperCase()
      var sections = parsed.sections || {}
      var names = []
      for (var key in sections) {
        if (["capabilities", "actions"].indexOf(key) === -1) names.push(key)
      }
      sectionNames = names
      selectedSection = names.indexOf("overview") !== -1 ? "overview" : (names[0] || "")
      rebuildDetails()
    } catch (error) {
      errorText = "The probe returned invalid structured data."
    }
  }

  function simple(value) {
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value === null
  }

  function addRows(value, prefix, depth) {
    if (depth > 5) { detailModel.append({ label: prefix, value: "…", depth: depth }); return }
    if (simple(value)) {
      detailModel.append({ label: prefix || "value", value: value === null ? "—" : String(value), depth: depth })
    } else if (Array.isArray(value)) {
      if (value.length === 0) detailModel.append({ label: prefix || "items", value: "None", depth: depth })
      for (var i = 0; i < Math.min(value.length, 300); i++) addRows(value[i], "[" + (i + 1) + "]", depth + 1)
      if (value.length > 300) detailModel.append({ label: "limit", value: (value.length - 300) + " more rows", depth: depth })
    } else if (value) {
      for (var key in value) addRows(value[key], String(key).replace(/_/g, " "), depth + 1)
    }
  }

  function rebuildDetails() {
    detailModel.clear()
    var sections = report.sections || {}
    addRows(sections[selectedSection], selectedSection, 0)
  }

  function selectSection(name) {
    selectedSection = String(name)
    rebuildDetails()
  }

  function refreshVision() {
    if ((!vision && !hud) || visionProcess.running) return
    visionProcess.command = ["python3", scriptPath, "--vision-json"]
    visionProcess.running = true
  }

  ListModel { id: detailModel }
  ListModel { id: visionModel }

  Process {
    id: dataProcess
    stdout: StdioCollector { id: dataOut; waitForEnd: true }
    stderr: StdioCollector { id: dataErr; waitForEnd: true }
    onExited: function(exitCode) {
      root.loading = false
      if (dataOut.text) root.loadReport(dataOut.text)
      else root.errorText = String(dataErr.text || "Probe failed").trim().substring(0, 300)
    }
  }

  Process {
    id: visionProcess
    stdout: StdioCollector { id: visionOut; waitForEnd: true }
    onExited: function(exitCode) {
      visionModel.clear()
      try {
        var data = JSON.parse(visionOut.text || "{}")
        var windows = data.windows || []
        for (var i = 0; i < windows.length; i++) visionModel.append(windows[i])
      } catch (error) { }
    }
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.vision || root.hud
    onTriggered: root.refreshVision()
  }

  Timer {
    interval: 2000
    repeat: true
    running: root.opened && ["PROCESS", "WINDOW", "INTERFACE", "SYSTEM"].indexOf(root.typeText) !== -1
    onTriggered: if (!dataProcess.running) root.inspect(root.activeTarget)
  }

  PanelWindow {
    id: panel
    visible: root.opened && !root.vision && !root.hud
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "omarchy-xray"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

    Rectangle { anchors.fill: parent; color: root.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

    Rectangle {
      id: card
      width: Math.min(Style.space(940), panel.width - Style.gapsOut * 2)
      height: Math.min(Style.space(700), panel.height - Style.gapsOut * 2)
      anchors.centerIn: parent
      radius: Style.cornerRadius
      color: root.background
      border.width: Math.max(1, Style.space(1))
      border.color: root.borderColor

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) { root.dismiss(); event.accepted = true }
          else if (event.key === Qt.Key_R && event.modifiers & Qt.ControlModifier) { root.inspect(root.activeTarget); event.accepted = true }
          else if (event.key === Qt.Key_1 && root.sectionNames.length > 0) { root.selectSection(root.sectionNames[0]); event.accepted = true }
        }

        ColumnLayout {
          anchors.fill: parent
          anchors.margins: Style.spacing.panelPadding
          spacing: Style.spacing.md

          RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.md

            Rectangle { width: Style.space(4); height: Style.space(42); radius: width / 2; color: root.accent }
            ColumnLayout {
              Layout.fillWidth: true
              spacing: 0
              Text { text: root.titleText; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
              Text { text: root.typeText + "  ·  LOCAL / READ ONLY"; color: root.accent; font.family: root.fontFamily; font.pixelSize: Style.font.caption; font.letterSpacing: 1.4 }
            }
            Text { text: root.loading ? "SCANNING" : "LIVE"; color: root.loading ? root.muted : root.accent; font.family: root.fontFamily; font.pixelSize: Style.font.caption; font.bold: true }
            Text { text: "ESC  CLOSE"; color: root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
          }

          Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor; opacity: 0.45 }

          RowLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.sm
            Rectangle {
              Layout.fillWidth: true
              height: Style.space(38)
              radius: Style.cornerRadius / 2
              color: Color.menu.selectedBackground
              border.width: 1
              border.color: root.borderColor
              TextInput {
                id: query
                anchors.fill: parent
                anchors.margins: Style.spacing.sm
                text: root.queryText
                color: root.foreground
                selectionColor: root.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                clip: true
                onTextChanged: root.queryText = text
                Keys.onReturnPressed: root.inspectQuery()
              }
              Text { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: Style.spacing.sm; visible: query.text.length === 0; text: "PID, :port, path, domain, IP, interface…"; color: root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.body }
            }
            Rectangle {
              width: Style.space(88); height: Style.space(38); radius: Style.cornerRadius / 2; color: root.accent
              Text { anchors.centerIn: parent; text: "INSPECT"; color: root.background; font.family: root.fontFamily; font.bold: true; font.pixelSize: Style.font.caption }
              MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.inspectQuery() }
            }
          }

          Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: Style.space(42)
            contentWidth: tabs.width
            clip: true
            Row {
              id: tabs
              spacing: Style.spacing.sm
              Repeater {
                model: root.sectionNames
                delegate: Rectangle {
                  required property string modelData
                  width: tabText.implicitWidth + Style.spacing.md * 2
                  height: Style.space(34)
                  radius: Style.cornerRadius / 2
                  color: root.selectedSection === modelData ? Color.menu.selectedBackground : "transparent"
                  border.width: root.selectedSection === modelData ? 1 : 0
                  border.color: root.accent
                  Text { id: tabText; anchors.centerIn: parent; text: modelData.toUpperCase(); color: root.selectedSection === modelData ? root.accent : root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.caption; font.bold: true }
                  MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.selectSection(modelData) }
                }
              }
            }
          }

          Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Style.cornerRadius / 2
            color: Qt.rgba(0, 0, 0, 0.12)
            border.width: 1
            border.color: Qt.rgba(root.borderColor.r, root.borderColor.g, root.borderColor.b, 0.35)

            Text { anchors.centerIn: parent; visible: root.errorText !== ""; width: parent.width * 0.8; text: root.errorText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: Color.urgent; font.family: root.fontFamily; font.pixelSize: Style.font.body }
            ListView {
              anchors.fill: parent
              anchors.margins: Style.spacing.md
              visible: root.errorText === ""
              model: detailModel
              clip: true
              spacing: Style.space(3)
              delegate: Rectangle {
                required property string label
                required property string value
                required property int depth
                width: ListView.view.width
                height: Math.max(Style.space(28), valueText.implicitHeight + Style.spacing.sm)
                color: "transparent"
                RowLayout {
                  anchors.fill: parent
                  anchors.leftMargin: Math.min(depth, 5) * Style.spacing.sm
                  spacing: Style.spacing.md
                  Text { Layout.preferredWidth: Math.min(Style.space(260), parent.width * 0.35); text: label.toUpperCase(); color: root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.caption; elide: Text.ElideRight }
                  Text { id: valueText; Layout.fillWidth: true; text: value; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WrapAnywhere; textFormat: Text.PlainText }
                }
              }
            }
          }

          Text { Layout.fillWidth: true; text: "CTRL+R REFRESH  ·  NO TELEMETRY  ·  NO SUDO"; horizontalAlignment: Text.AlignRight; color: root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
        }
      }
    }
  }

  Variants {
    model: Quickshell.screens
    delegate: PanelWindow {
      id: visionWindow
      required property var modelData
      screen: modelData
      visible: root.vision || root.hud
      anchors { top: true; bottom: true; left: true; right: true }
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: "omarchy-xray-vision"
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

      Repeater {
        model: visionModel
        delegate: Rectangle {
          required property int pid
          required property string application
          required property string title
          required property var at
          required property var size
          required property string monitor_name
          required property string memory
          required property string threads
          visible: visionWindow.screen && monitor_name === visionWindow.screen.name
                   && (root.vision || pid === root.hudPid)
          x: Math.max(8, at[0] + 12)
          y: Math.max(8, at[1] + 12)
          width: Math.min(Style.space(310), Math.max(Style.space(190), size[0] - 24))
          height: Style.space(86)
          radius: Style.cornerRadius / 2
          color: root.background
          border.width: Math.max(1, Style.space(1))
          border.color: root.accent
          opacity: 0.94
          Column {
            anchors.fill: parent
            anchors.margins: Style.spacing.sm
            spacing: Style.space(3)
            Text { width: parent.width; text: application.toUpperCase(); color: root.accent; font.family: root.fontFamily; font.pixelSize: Style.font.caption; font.bold: true; elide: Text.ElideRight }
            Text { width: parent.width; text: title; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall; elide: Text.ElideRight }
            Text { width: parent.width; text: "PID " + pid + "   RAM " + memory + "   THREADS " + threads; color: root.muted; font.family: root.fontFamily; font.pixelSize: Style.font.caption; elide: Text.ElideRight }
          }
        }
      }
    }
  }
}
