<?php

define('DBNAME', "temperature");
define('DBUSER', "temperature");
define('DBPASS', "Oyi0o?109Mxje9_978");
define('DBHOST', "localhost");
define('DBTABLE', 'temperature');

define('HISTORY_RETAIN', 86400 * 365); // keep one year of log
define('ESP_TIME_GAP', 946684801); // esp32 time.time epoch starts from 2000

define('LOCATIONS', array("garage", "fermentatore1", "fermentatore2"));

define('TARGET_TEMP', array(
    "fermentatore1" => 20,
    "fermentatore2" => 20,
));
