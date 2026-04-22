// Google Apps Script для Кадровый автопилот
// Вставить в: script.google.com -> New Project
// Deploy -> New deployment -> Web app -> Execute as me, Anyone

// ID вашей Google Таблицы (после /d/ в URL таблицы)
var SHEET_ID = "1JS9iTtGaBCC2ElW-BaGRiLZh10-T8F8NJF6_ZLMdewg";

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);

    if (data.action === "new_user") {
      var ss = SpreadsheetApp.openById(SHEET_ID);
      var sheet = ss.getSheetByName("Лист1");
      
      if (!sheet) {
        sheet = ss.getSheets()[0];
      }
      
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
        .createTextOutput(JSON.stringify({status: "ok"}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    if (data.action === "update_user") {
      var ss = SpreadsheetApp.openById(SHEET_ID);
      var sheet = ss.getSheetByName("Лист1");
      if (!sheet) sheet = ss.getSheets()[0];
      
      // Ищем строку по email (колонка C)
      var dataRange = sheet.getDataRange();
      var values = dataRange.getValues();
      
      for (var i = 1; i < values.length; i++) {
        if (values[i][2] && values[i][2].toString().toLowerCase() === data.email.toLowerCase()) {
          // Обновляем ячейки если переданы новые значения
          if (data.name) sheet.getRange(i + 1, 2).setValue(data.name);
          if (data.telegram) sheet.getRange(i + 1, 4).setValue(data.telegram);
          if (data.employees !== undefined) sheet.getRange(i + 1, 5).setValue(data.employees);
          break;
        }
      }
      
      return ContentService
        .createTextOutput(JSON.stringify({status: "ok"}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({status: "ignored"}))
      .setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status: "error", message: err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({status: "ok"}))
    .setMimeType(ContentService.MimeType.JSON);
}
