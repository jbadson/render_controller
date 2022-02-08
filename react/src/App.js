import React, { Component } from 'react';
import './App.css';
import axios from 'axios';
import JobInput from './JobInput';
import QueuePane from './QueuePane';
import JobStatusPane from './JobStatus';
import SettingsWidget from './SettingsWidget';


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

  toggleInputPane(callback = null) {
    if (callback.job_id) {
      // Job was successfully created, so select it
      this.selectJob(callback.job_id)
    }
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
    axios.post(process.env.REACT_APP_BACKEND_API + "/config/autostart/" + action)
      .then(result => {this.getAutostart()}); // Updates checkbox state
  }

  getAutostart() {
    axios.get(process.env.REACT_APP_BACKEND_API + "/config/autostart")
      .then(
        result => {this.setState({autostart: result.data.autostart})},
        error => {console.error(error.message)}
      );
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(process.env.REACT_APP_BACKEND_API + "/job/info")
      .then(
        result => {this.setState({serverJobs: result.data})},
        error => {this.setState({error: error})}
      )
      .then(() => {this.sortJobs();})
      .then(() => {
        // Select first job if none are selected
        this.selectFirstJob();
      }
      )
  }

  /**
   * Sorts jobs for the queue pane.  Rendering jobs go first and Finished
   * jobs go last.  Everything else goes in between with server order preserved.
   */
  sortJobs() {
    const jobList = this.state.serverJobs;
    const jobsRendering = jobList.filter(job => job.status === "Rendering")
    const jobsFinished = jobList.filter(job => job.status === "Finished")
    const jobsOther = jobList.filter(job => job.status !== "Rendering")
      .filter(job => job.status !== "Finished")

    const sortedJobs = [...jobsRendering, ...jobsOther, ...jobsFinished]
    this.setState({
      serverJobs: sortedJobs
    })
  }

  selectFirstJob() {
    const { selectedJob, serverJobs } = this.state;
    if (!selectedJob && serverJobs.length > 0) {
      this.selectJob(serverJobs[0].id);
    }
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), process.env.REACT_APP_POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderContentPane() {
    if (this.state.showInputPane) {
      return (
        <JobInput
          path=""
          onClose={this.toggleInputPane}
        />
      )
    } else if (this.state.selectedJob) {
      return (
        <JobStatusPane
          jobId={this.state.selectedJob}
          onDelete={this.deselectJob}
        />
      )
    }
    return;
  }

  renderSettingsWidget() {
    if (!this.state.showSettings) {
      return;
    }
    return (
      <SettingsWidget
        autostart={this.state.autostart}
        onClose={this.toggleSettings}
        toggleAutostart={this.toggleAutostart}
      />
    )
  }

  checkFocus() {
    if (this.state.showInputPane) {
      return (<div className="grayover">&nbsp;</div>)
    }
  }

  render() {
    const { serverJobs, selectedJob, showSettings, error } = this.state;
    if (error) {
      return <p>Error: {error.message}</p>
    }
    return (
      <ul>
        <li className="layout-row">
          <button className="button-left" onClick={this.toggleInputPane}>New</button>
          <div className="right">
            <button className="button-left" disabled={showSettings} onClick={this.toggleSettings}>Settings</button>
            {this.renderSettingsWidget()}
          </div>
        </li>
        <li className="layout-row">
            {this.checkFocus()}
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
    )
  }
}


export default App;
