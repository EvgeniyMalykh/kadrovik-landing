// Google Apps Script для Кадровый автопилот
var SHEET_ID = "1JS9iTtGaBCC2ElW-BaGRiLZh10-T8F8NJF6_ZLMdewg";

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = ss.getSheetByName("Лист1");
    if (!sheet) sheet = ss.getSheets()[0];

    if (data.action === "new_user") {
      sheet.appendRow([
        data.date || new Date().toLocaleString("ru-RU"),
        data.name || "",
        data.email || "",
        data.telegram || "",
        data.employees !== undefined ? String(data.employees) : "",
        data.source || "Регистрация"
      ]);
      return ContentService
        .createTextOutput(JSON.stringify({status: "ok", action: "new_user"}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (data.action === "update_user") {
      var values = sheet.getDataRange().getValues();
      for (var i = 1; i < values.length; i++) {
        if (values[i][2] && values[i][2].toString().trim().toLowerCase() === data.email.trim().toLowerCase()) {
          if (data.name) sheet.getRange(i + 1, 2).setValue(data.name);
          if (data.telegram) sheet.getRange(i + 1, 4).setValue(data.telegram);
          if (data.employees !== undefined) sheet.getRange(i + 1, 5).setValue(String(data.employees));
          return ContentService
            .createTextOutput(JSON.stringify({status: "updated", row: i + 1}))
            .setMimeType(ContentService.MimeType.JSON);
        }
      }
      return ContentService
        .createTextOutput(JSON.stringify({status: "not_found", email: data.email}))
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
    .createTextOutput(JSON.stringify({status: "ok", message: "Кадровый автопилот webhook is running"}))
    .setMimeType(ContentService.MimeType.JSON);
}
