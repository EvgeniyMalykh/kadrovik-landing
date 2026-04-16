// Google Apps Script для Кадровый автопилот
// Вставить в: script.google.com -> New Project

// ID вашей Google Таблицы (после /d/ в URL таблицы)
var SHEET_ID = "ВСТАВЬТЕ_ID_ТАБЛИЦЫ_СЮДА";

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);

    if (data.action === "new_user") {
      var ss = SpreadsheetApp.openById(SHEET_ID);
      var sheet = ss.getSheetByName("Пользователи");
      
      // Создаём лист если нет
      if (!sheet) {
        sheet = ss.insertSheet("Пользователи");
        sheet.appendRow(["Дата регистрации", "Email", "Компания", "Тариф"]);
        // Форматирование заголовков
        sheet.getRange(1, 1, 1, 4).setBackground("#1a56db").setFontColor("#ffffff").setFontWeight("bold");
      }
      
      sheet.appendRow([
        data.date || new Date().toLocaleString("ru-RU"),
        data.email,
        data.company,
        "TRIAL (7 дней)"
      ]);
      
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
