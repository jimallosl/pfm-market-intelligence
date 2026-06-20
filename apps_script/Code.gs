function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || "{}");
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    writeSummary_(ss, payload.summary || {});
    writeRows_(ss, "raw_pages", payload.raw_pages || [], [
      "run_id","captured_at","source_group","source_name","source_class","quality_estimate","influence_estimate",
      "data_type","confidence_level","url","status","title","text_length","screenshot_path","html_path","error","text"
    ]);
    writeRows_(ss, "extracted_signals", payload.extracted_signals || [], [
      "run_id","captured_at","source_group","source_name","source_class","quality_estimate","influence_estimate",
      "url","signal_type","signal_value","surrounding_text","data_type","confidence_level","extraction_method"
    ]);
    writeRows_(ss, "errors", payload.errors || [], [
      "run_id","captured_at","source_group","source_name","source_class","quality_estimate","influence_estimate",
      "data_type","confidence_level","url","status","title","text_length","screenshot_path","html_path","error","text"
    ]);
    return ContentService.createTextOutput(JSON.stringify({ok:true, received_at:new Date().toISOString()})).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ok:false, error:String(err)})).setMimeType(ContentService.MimeType.JSON);
  }
}
function writeSummary_(ss, summary) {
  const sh = getOrCreateSheet_(ss, "run_log", ["received_at","run_id","captured_at","raw_pages","signals","errors","out_dir"]);
  sh.appendRow([new Date().toISOString(), summary.run_id || "", summary.captured_at || "", summary.raw_pages || 0, summary.signals || 0, summary.errors || 0, summary.out_dir || ""]);
}
function writeRows_(ss, sheetName, rows, headers) {
  const sh = getOrCreateSheet_(ss, sheetName, headers);
  if (!rows.length) return;
  const values = rows.map(r => headers.map(h => {
    const v = r[h];
    if (v === null || v === undefined) return "";
    const s = String(v);
    return s.length > 45000 ? s.substring(0, 45000) : s;
  }));
  sh.getRange(sh.getLastRow() + 1, 1, values.length, headers.length).setValues(values);
}
function getOrCreateSheet_(ss, name, headers) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
    sh.autoResizeColumns(1, headers.length);
  } else if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
  }
  return sh;
}
