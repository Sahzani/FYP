<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Dashboard with Breadcrumb</title>
<style>
  /* Reset */
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  html, body {
    height: 100%;
    font-family: 'Roboto', sans-serif;
    background: linear-gradient(75.18deg, #FFE5B4 36.63%, #F5EEDC 92.2%);
    color: #333;
  }

  /* Fixed header */
  header {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 60px;
    background: #fff;
    box-shadow: 0 2px 20px rgba(1, 41, 112, 0.1);
    display: flex;
    align-items: center;
    padding-left: 20px;
    font-family: 'Nunito', sans-serif;
    font-weight: 700;
    font-size: 26px;
    color: #212529;
    z-index: 10;
  }

  /* Breadcrumb container */
  .breadcrumb {
    position: absolute;
    width: 1200px;
    height: 50px;
    left: 368px;
    top: 84px;
    font-family: 'Nunito', sans-serif;
    z-index: 9;
  }

  /* Breadcrumb ol */
  .breadcrumb ol {
    position: absolute;
    width: 1152px;
    height: 21px;
    left: 0;
    top: 28.8px;
    display: flex;
    list-style: none;
    padding: 0;
    margin: 0;
    align-items: flex-start;
  }

  /* Breadcrumb list items container */
  .breadcrumb ol li {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    gap: 7.17px;
    padding-left: 8px;
    height: 21px;
    position: relative;
  }

  /* Home link */
  .breadcrumb-home {
    font-weight: 600;
    font-size: 14px;
    line-height: 21px;
    color: #989797;
    text-decoration: none;
    width: 38.5px;
    height: 19px;
    display: flex;
    align-items: center;
  }
  .breadcrumb-home:hover {
    text-decoration: underline;
  }

  /* Separator "/" */
  .separator {
    font-weight: 600;
    font-size: 14px;
    line-height: 21px;
    color: #989797;
    width: 5px;
    height: 21px;
    display: flex;
    align-items: center;
  }

  /* Current breadcrumb text */
  .breadcrumb-current {
    font-weight: 600;
    font-size: 14px;
    line-height: 21px;
    color: #444444;
    display: flex;
    align-items: center;
    width: 70px;
    height: 21px;
    flex: none;
    order: 1;
    flex-grow: 0;
  }

  /* Main content container with padding top to avoid header and breadcrumb overlap */
  main {
    padding: 140px 20px 20px; /* 60px header + 50px breadcrumb + some spacing */
    max-width: 1200px;
    margin: 0 auto;
  }

  /* Metrics Cards */
  .metrics {
    display: flex;
    gap: 20px;
    margin-bottom: 30px;
    flex-wrap: wrap;
  }
  .card {
    background: white;
    flex: 1 1 150px;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgb(0 0 0 / 0.1);
    display: flex;
    align-items: center;
    gap: 15px;
  }
  .card .icon {
    font-size: 30px;
    color: #4a90e2;
  }
  .card .content {
    flex-grow: 1;
  }
  .card .content .number {
    font-size: 24px;
    font-weight: 700;
  }
  .card.students .icon {
    color: #4a90e2;
  }
  .card.teachers .icon {
    color: #50b948;
  }
  .card.classes .icon {
    color: #f5a623;
  }

  /* Attendance Summary */
  .attendance-summary {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgb(0 0 0 / 0.1);
    margin-bottom: 30px;
  }
  .attendance-summary h2 {
    margin-top: 0;
  }
  .attendance-details {
    display: flex;
    gap: 40px;
    margin-top: 10px;
  }
  .attendance-item {
    flex: 1;
    font-size: 18px;
  }
  .attendance-item.present {
    color: #50b948;
  }
  .attendance-item.absent {
    color: #d9534f;
  }
  /* Simple bar */
  .bar-container {
    background: #eee;
    border-radius: 10px;
    height: 20px;
    width: 100%;
    margin-top: 15px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 10px 0 0 10px;
    background: #50b948;
    width: 90%; /* example percentage */
  }

  /* System Logs */
  .system-logs {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgb(0 0 0 / 0.1);
    margin-bottom: 30px;
  }
  .system-logs h2 {
    margin-top: 0;
  }
  .log-list {
    list-style: none;
    padding-left: 0;
    max-height: 150px;
    overflow-y: auto;
  }
  .log-list li {
    padding: 8px 0;
    border-bottom: 1px solid #eee;
    font-size: 14px;
  }

  /* Quick Actions */
  .quick-actions {
    display: flex;
    gap: 15px;
    flex-wrap: wrap;
  }
  .quick-actions button {
    flex: 1 1 150px;
    padding: 15px;
    border: none;
    background: #4a90e2;
    color: white;
    font-weight: 700;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.3s ease;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
  }
  .quick-actions button:hover {
    background: #357abd;
  }
  .quick-actions button .icon {
    font-size: 18px;
  }

  /* Responsive */
  @media (max-width: 600px) {
    .metrics, .quick-actions, .attendance-details {
      flex-direction: column;
    }
    .card, .quick-actions button {
      flex: 1 1 100%;
    }

    .breadcrumb {
      position: static;
      width: auto;
      height: auto;
      margin-bottom: 20px;
      left: auto;
      top: auto;
    }

    .breadcrumb ol {
      position: static;
      width: auto;
      height: auto;
      flex-wrap: wrap;
    }
  }
</style>

<!-- Icons from Google Material Icons -->
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet" />

</head>
<body>

<header>iAttend</header>

<nav class="breadcrumb" aria-label="Breadcrumb">
  <ol>
    <li><a href="#" class="breadcrumb-home">Home</a></li>
    <li class="separator">/</li>
    <li class="breadcrumb-current">Dashboard</li>
  </ol>
</nav>

<main>

  <section class="metrics" aria-label="Key system metrics">
    <div class="card students">
      <span class="material-icons icon" aria-hidden="true">groups</span>
      <div class="content">
        <div class="number">500</div>
        <div>Total Students</div>
      </div>
    </div>
    <div class="card teachers">
      <span class="material-icons icon" aria-hidden="true">person</span>
      <div class="content">
        <div class="number">30</div>
        <div>Total Teachers</div>
      </div>
    </div>
    <div class="card classes">
      <span class="material-icons icon" aria-hidden="true">class</span>
      <div class="content">
        <div class="number">20</div>
        <div>Total Classes</div>
      </div>
    </div>
  </section>

  <section class="attendance-summary" aria-label="Today's attendance summary">
    <h2>Today's Attendance Summary</h2>
    <div class="attendance-details">
      <div class="attendance-item present">
        Present: 450 (90%)
      </div>
      <div class="attendance-item absent">
        Absent: 50 (10%)
      </div>
    </div>
    <div class="bar-container" aria-label="Attendance percentage bar">
      <div class="bar-fill"></div>
    </div>
  </section>

  <section class="system-logs" aria-label="Recent system logs">
    <h2>System Logs Preview</h2>
    <ul class="log-list">
      <li>2025-08-05: User John Doe registered</li>
      <li>2025-08-05: Class 10A created</li>
      <li>2025-08-04: Attendance uploaded</li>
    </ul>
  </section>

  <section class="quick-actions" aria-label="Quick actions">
    <button><span class="material-icons icon" aria-hidden="true">person_add</span> Add User</button>
    <button><span class="material-icons icon" aria-hidden="true">add_box</span> Add Class</button>
    <button><span class="material-icons icon" aria-hidden="true">face</span> Upload Faces</button>
  </section>

</main>

</body>
</html>
