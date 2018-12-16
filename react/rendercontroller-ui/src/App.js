import React, { Component } from 'react';
import './App.css';
import axios from 'axios';
import JobInput from './JobInput';
import QueuePane from './QueuePane';
import JobStatusPane from './JobStatus';
import CheckBox from './CheckBox'
import {FileBrowserPopup} from './FileBrowser';

/* TODO:
- Make settings menu checkbox update after click
- Order queue boxes by queue position (or queue time)
- Disable (preferably gray out or hide) buttons in irrelevant contexts:
  Enqueue when state != stopped
  Start when state == running
- Tooltips for buttons, especially start, stop, enqueue
- Finish styling
- Review all FIXMEs and TODOs
- Figure out how to package this for distribution
*/

const POLL_INTERVAL = 1000; // Milliseconds
const API_CONNECT = "http://localhost:2020";


/**
 * Displays settings in a popup overlay.
 * @param {boolean} autostart - State of autostart setting
 * @param {function} onClose - Action to take when window is closed.
 * @param {function} toggleAutostart - Callback to flip state of autostart
 */
function SettingsPopup(props) {
  return (
    <div className="settings-overlay">
      <div className="settings-container">
        <ul>
          <li className="settings-row">
            <div className="settings-header">
              Settings
              <div className="settings-closebutton" onClick={props.onClose}>X</div>
            </div>
          </li>
          <li className="layout-row">
            <div className="settings-inner">
              <CheckBox
                label="Automatically start renders"
                checked={props.autostart}
                onChange={props.toggleAutostart}
              />
            </div>
          </li>
        </ul>
      </div>
    </div>
  )
}



class App extends Component {
  constructor(props) {
    super(props);
    this.state = {
      selectedJob: null,
      serverJobs: [],
      error: null,
      showInputPane: false,
      showSettings: false,
      autostart: true,
    }
    this.selectJob = this.selectJob.bind(this);
    this.toggleInputPane = this.toggleInputPane.bind(this);
    this.toggleSettings = this.toggleSettings.bind(this);
    this.toggleAutostart = this.toggleAutostart.bind(this);
    this.deselectJob = this.deselectJob.bind(this);
  }

  selectJob(jobId) {
    this.setState({selectedJob: jobId})
  }

  deselectJob() {
    this.setState({selectedJob: null});
    this.selectFirstJob();
  }

  toggleInputPane() {
    this.setState(state => ({showInputPane: !state.showInputPane}))
  }

  toggleSettings() {
    if (!this.state.showSettings) {
      this.getAutostart();
    }
    this.setState(state => ({showSettings: !state.showSettings}))
  }

  toggleAutostart() {
    let action = "enable";
    if (this.state.autostart) {
      action = "disable";
    }
    axios.post(API_CONNECT + "/config/autostart/" + action)
      .then(this.getAutostart())
  }

  getAutostart() {
    axios.get(API_CONNECT + "/config/autostart")
      .then(
        result => {this.setState({autostart: result.data.autostart})},
        error => {console.error(error.message)}
      )
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(API_CONNECT + "/job/summary")
      .then(
        result => {this.setState({serverJobs: result.data})},
        error => {this.setState({error: error})}
      )
      .then(() => {
        // Select first job if none are selected
        this.selectFirstJob();
      }
      )
  }

  selectFirstJob() {
    const { selectedJob, serverJobs } = this.state;
    if (!selectedJob && serverJobs.length > 0) {
      this.selectJob(serverJobs[0].id);
    }
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderContentPane() {
    if (this.state.showInputPane) {
      return (
        <JobInput
          path="/"
          url={API_CONNECT}
          onClose={this.toggleInputPane}
        />
      )
    } else if (this.state.selectedJob) {
      return (
        <JobStatusPane
          jobId={this.state.selectedJob}
          url={API_CONNECT}
          pollInterval={POLL_INTERVAL}
          onDelete={this.deselectJob}
        />
      )
    }
    return;
  }

  renderSettingsPopup() {
    if (!this.state.showSettings) {
      return;
    }
    return (
      <SettingsPopup
        autostart={this.state.autostart}
        onClose={this.toggleSettings}
        toggleAutostart={this.toggleAutostart}
      />
    )
  }

  render() {
    const { serverJobs, selectedJob, error } = this.state;
    if (error) {
      return <p>Error: {error.message}</p>
    }
    return (
      <div>
        {this.renderSettingsPopup()}
        <ul>
          <li className="layout-row">
            <button className="button-left" onClick={this.toggleInputPane}>New</button>
            <button className="button-right" onClick={this.toggleSettings}>Settings</button>
          </li>
          <li className="layout-row">
            <div className="sidebar">
              <QueuePane
                serverJobs={serverJobs}
                onJobClick={this.selectJob}
                selectedJob={selectedJob}
              />
            </div>
            <div className="content-pane">
              {this.renderContentPane()}
            </div>
          </li>
        </ul>
      </div>
    )
  }
}


export default App;
