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

function _disconnect($dbh)
{
    $dbh->close();
}

function read_from_db($dbh, $show, $location)
{
    $now = time();
    if ($show == "d") {
        $older = $now - ESP_TIME_GAP - 86400;
    } else if ($show == "w") {
        $older = $now - ESP_TIME_GAP - (86400 * 7);
    } else if ($show == "m") {
        $older = $now - ESP_TIME_GAP - (86400 * 31);
    } else if ($show == "y") {
        $older = $now - ESP_TIME_GAP - (86400 * 365);
    } else {
        $older = $now - ESP_TIME_GAP - (86400 * 7);
    }

    $stmt = $dbh->prepare("SELECT ts, temperature FROM " . DBTABLE . " WHERE ts > ? and location = ? ORDER BY ts");
    $stmt->bind_param("is", $older, $location);

    $stmt->execute();
    $results = $stmt->get_result();
    $values = array();
    $labels = array();

    $pre_hour = 99;
    $pre_day = 99;
    $pre_month = 99;
    $this_label = 99;
    $last_insert_time = 0;
    $count = 0;
    $sum = 0;

    while ($row = $results->fetch_assoc()) {
        //$val = intval(floatval($row["temperature"]) * 10);
        $val = $row["temperature"];
        $this_hour = date("H", $row["ts"]);
        $this_day = date("d", $row["ts"]);
        $this_month = date("m", $row["ts"]);
        $last_insert_time = $row["ts"];

        if ($this_label == 99) {
            $this_label = $this_hour . "\n" . $this_day . "|" . $this_month;
        }
        if ($pre_hour == 99) {
            $pre_hour = $this_hour;
        }
        if ($pre_day == 99) {
            $pre_day = $this_day;
        }
        if ($pre_month == 99) {
            $pre_month = $this_month;
        }

        if ($pre_hour != $this_hour) {
            //$media = intval($sum / $count);
            $media = intval($sum * 10 / $count) / 10;
            array_push($values, $media);
            array_push($labels, $this_label);
            $count = 0;
            $sum = 0;
            $pre_hour = $this_hour;
            if ($pre_month != $this_month) {
                $this_label = $this_hour . "\n" . $this_day . "|" . $this_month;
                $pre_month = $this_month;
                $pre_day = $this_day;
            } else if ($pre_day != $this_day) {
                $this_label = $this_hour . "\n" . $this_day;
                $pre_day = $this_day;
            } else {
                $this_label = $this_hour;
            }
        }
        $sum = $sum + $val;
        $count++;
    }
    $stmt->close();

    //$media = intval($sum / $count);
    if ($count > 0) {
        $media = intval($sum * 10 / $count) / 10;
        array_push($values, $media);
        array_push($labels, $this_label);
    }
    return array($values, $labels, $last_insert_time);
}

function show_history($show, $location, $target_temp)
{
    require_once('_jpgraph/jpgraph.php');
    require_once('_jpgraph/jpgraph_line.php');

    $dbh = _connect();
    list($values, $labels, $last_insert_time) = read_from_db($dbh, $show, $location);
    // Setup the graph
    $graph = new Graph(1400, 250);
    $graph->SetScale("lin");
    $graph->SetMargin(40, 40, 36, 63);
    $graph->legend->SetFrameWeight(1);

    $graph->yaxis->HideZeroLabel();
    $graph->yaxis->HideLine(false);
    $graph->yaxis->HideTicks(false, false);
    $graph->xgrid->Show();
    $graph->xaxis->SetTickLabels($labels);

    // print target_temp, draw first because of a scale SNAFU
    if (!($target_temp === False)) {
        $limits = array();
        foreach ($values as $key => $value) {
            $limits[$key] = $target_temp;
        }
        $p3 = new LinePlot($limits);
        $graph->Add($p3);
        $p3->SetWeight(2);
        $p3->SetColor("red");
        $p3->SetStyle("dashed");
    }

    // right Y scale
    $graph->SetY2Scale('lin');
    $scaley2 = new LinePlot($values);
    $graph->AddY2($scaley2);
    $scaley2->SetWeight(-1);

    // main line
    $p1 = new LinePlot($values);
    $graph->Add($p1);
    $p1->SetWeight(2);
    $p1->SetColor("blue");
    $p1->SetStyle("solid");


    $graph->img->SetAntiAliasing(false); // required to have SetWeigth, keep it last

    // Output line
    if ($last_insert_time < 1000000000) {
        $last_insert_time = $last_insert_time + ESP_TIME_GAP;
    }

    $title = $location . " - " . date(DATE_RFC2822, $last_insert_time);
    $graph->title->Set($title);
    $graph->Stroke();
    _disconnect($dbh);
}

if (isset($_GET['show'])) {
    if ((isset($_GET["l"])) and (in_array($_GET["l"], LOCATIONS))) {
        $location = $_GET["l"];
        if (array_key_exists("target_temp", $_GET)) {
            $target_temp = $_GET["target_temp"];
        } else {
            $target_temp = False;
        }
        show_history($_GET['show'], $location, $target_temp);
    }
}
