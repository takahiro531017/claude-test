const path = require("path");
const express = require("express");

require("./seed");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, "..", "public")));

app.use("/api/locations", require("./routes/locations"));
app.use("/api/products", require("./routes/products"));
app.use("/api/movements", require("./routes/movements"));

app.listen(PORT, () => {
  console.log(`在庫管理アプリを起動しました: http://localhost:${PORT}`);
});
