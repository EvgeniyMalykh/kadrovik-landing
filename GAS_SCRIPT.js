// Google Apps Script для Кадровый автопилот
// Вставить в: script.google.com -> New Project
// Deploy -> New deployment -> Web app -> Execute as me, Anyone

// ID вашей Google Таблицы (после /d/ в URL таблицы)
var SHEET_ID = "1JS9iTtGaBCC2ElW-BaGRiLZh10-T8F8NJF6_ZLMdewg";

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = ss.getSheetByName("Лист1");
    if (!sheet) {
      sheet = ss.getSheets()[0];
    }

    if (data.action === "new_user") {
      // Колонки: A=Дата, B=Имя, C=Email, D=Telegram, E=Сотрудников, F=Источник
      sheet.appendRow([
        data.date || new Date().toLocaleString("ru-RU"),
        data.name || data.company || "",
        data.email || "",
        data.telegram || "",
        data.employees || 0,
        data.source || "Регистрация"
      ]);

      return ContentService
        .createTextOutput(JSON.stringify({status: "ok", action: "new_user"}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (data.action === "update_user") {
      // Ищем строку по email (колонка C, индекс 2)
      var dataRange = sheet.getDataRange();
      var values = dataRange.getValues();
      var found = false;

      for (var i = 1; i < values.length; i++) {
        if (values[i][2] && values[i][2].toString().trim().toLowerCase() === data.email.trim().toLowerCase()) {
          // Обновляем ячейки — записываем даже пустые значения чтобы очистить
          if (data.name !== undefined && data.name !== null && data.name !== "") {
            sheet.getRange(i + 1, 2).setValue(data.name);      // B = Имя
          }
          if (data.telegram !== undefined && data.telegram !== null && data.telegram !== "") {
            sheet.getRange(i + 1, 4).setValue(data.telegram);  // D = Telegram
          }
          if (data.employees !== undefined && data.employees !== null) {
            sheet.getRange(i + 1, 5).setValue(data.employees);  // E = Сотрудников
          }
          found = true;
          return ContentService
            .createTextOutput(JSON.stringify({status: "updated", row: i + 1, email: data.email}))
            .setMimeType(ContentService.MimeType.JSON);
        }
      }

      if (!found) {
        return ContentService
          .createTextOutput(JSON.stringify({status: "not_found", email: data.email, rows_checked: values.length}))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }

    return ContentService
      .createTextOutput(JSON.stringify({status: "ignored", action: data.action || "none"}))
      .setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status: "error", message: err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({status: "ok", message: "Кадровый автопилот webhook is running"}))
    .setMimeType(ContentService.MimeType.JSON);
}
