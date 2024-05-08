<?php
require_once('config.php');

function _connect()
{

    // Create connection
    $dbh = new mysqli(DBHOST, DBUSER, DBPASS, DBNAME);

    if ($dbh->connect_error) {
        die("Connection failed: " . $dbh->connect_error);
    }
    return $dbh;
}

function garbage_collection($dbh)
{
    if (rand(0, 1000)) {
        return;
    }
    $now = time();

    // delete temperatures
    $where = $now - HISTORY_RETAIN - ESP_TIME_GAP;
    $sql = "DELETE from " . DBTABLE . " where ts < $where";
    $dbh->query($sql);

    // delete logs
    $sql = "DELETE FROM  " . DBTABLE . "_log WHERE timestamp < (NOW() - INTERVAL 1 MONTH)";
    $dbh->query($sql);
}

function _disconnect($dbh)
{
    $dbh->close();
}

function add_to_db($th, $time, $location)
{
    $dbh = _connect();

    // prepare and bind
    if ($location === "log") {
        $stmt = $dbh->prepare("INSERT INTO " . DBTABLE . "_log (ts, message) VALUES (?, ?)");
        $stmt->bind_param("is", $time, $th);
    } else {
        $stmt = $dbh->prepare("INSERT INTO " . DBTABLE . " (ts, location, temperature) VALUES (?, ?, ?)");
        $stmt->bind_param("iss", $time, $location, $th);
    }

    $stmt->execute();

    $stmt->close();
    garbage_collection($dbh);
    _disconnect($dbh);
}

function get_target_temp($location)
{
    if (defined('TARGET_TEMP') && array_key_exists($location, TARGET_TEMP)) {
        $target_temp = TARGET_TEMP[$location];
    } else {
        $target_temp = False;
    }
    return $target_temp;
}

function show_history($show, $location)
{
    $target_temp = get_target_temp($location);
    echo '<pre>';
    echo '<img src="graph.php?l=' . $location . '&show=' . $show;
    if (!($target_temp === False)) {
        echo '&target_temp=' . $target_temp;
    }
    echo '">';
    echo '</pre>';
}

function show_log()
{
    $dbh = _connect();
    /*
    # show last receive
    echo "<pre>\n<table border='1'>\n<tr>\n";
    foreach (LOCATIONS as $location) {
        echo "<th>" . $location . "</th>\n";
    }
    echo "</tr>\n";
    echo "<tr>\n";
    foreach (LOCATIONS as $table) {
        $sql = "SELECT ts, temperature from " . TABLE_PREFIX . "$table order by ts DESC limit 0,1";
        $result = $dbh->query($sql);
        while ($row = mysqli_fetch_assoc($result)) {
            if ($row["ts"] < 1000000000) {
                $real_ts = $row["ts"] + ESP_TIME_GAP;
            } else {
                $real_ts = $row["ts"];
            }

            $date = date(DATE_RFC2822, $real_ts);
            echo "<td>$date</td>\n";
        }
    }
    echo "</tr>\n";
    echo "</table></pre>\n";
    */
    # show logs
    echo '<pre>';
    $sql = "SELECT ts, message from " . DBTABLE . "_log order by insert_time DESC limit 0,100";
    $result = $dbh->query($sql);
    while ($row = mysqli_fetch_assoc($result)) {
        if ($row["ts"] < 1000000000) {
            $real_ts = $row["ts"] + ESP_TIME_GAP;
        } else {
            $real_ts = $row["ts"];
        }
        $log_date = date(DATE_RFC2822, $real_ts);
        echo $log_date . ": " . htmlspecialchars($row["message"]) . "<br>";
    }
    _disconnect($dbh);
    echo '</pre>';
}

// main
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $_REQUEST = json_decode(file_get_contents('php://input'), true);
}

// handle request from python, add measure to the database
if (isset($_REQUEST['th']) && isset($_REQUEST['time'])) {
    if (!(isset($_REQUEST['l'])) || ((!(in_array($_REQUEST['l'], LOCATIONS)))) && (!($_REQUEST['l'] == "log"))) {
        error_log(("112Unknown location " . $_REQUEST['l']));
        exit;
    }
    $location = $_REQUEST['l'];
    add_to_db($_REQUEST['th'], intval($_REQUEST['time']), $location);
    exit;
}

// supposely human, show data
if ((isset($_REQUEST['show']) || array_key_exists('show', $_REQUEST))) {
    $show = $_REQUEST['show'];
    if (!(in_array($show, array("d", "w", "y")))) {
        $show = "w";
    }
    echo "<html><head><META HTTP-EQUIV='Refresh' CONTENT=300;></head>\n";
    echo "<body>";
    if ((isset($_REQUEST["l"])) and (in_array($_REQUEST["l"], LOCATIONS))) {
        $location = $_REQUEST["l"];
        show_history($_REQUEST['show'], $_REQUEST["l"]);
    } else {
        foreach (LOCATIONS as $location) {
            if ($location != "log") {
                show_history($_REQUEST['show'], $location);
            }
        }
        show_log();
    }
    echo "</body>\n</html>";
}
