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
    this.clearFinishedJobs = this.clearFinishedJobs.bind(this);
  }

  selectJob(jobId) {
    this.setState({selectedJob: jobId})
  }

  selectFirstJob() {
    const { selectedJob, serverJobs } = this.state;
    if (!selectedJob && serverJobs.length > 0) {
      this.selectJob(serverJobs[0].id);
    }
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

  clearFinishedJobs() {
    const { serverJobs, selectedJob } = this.state;
    serverJobs.forEach(job => {
      if (job.status === "Finished") {
        if (selectedJob === job.id) {
          // Deselect job to prevent status pane from making API calls with deleted job id.
          this.setState({selectedJob: null});
        }
        axios.post(process.env.REACT_APP_BACKEND_API + "/job/delete/" + job.id)
          .then(
            (error) => {console.error(error.message)}
          );
      }
    })
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
   * Sorts jobs for the queue pane.
   */
  sortJobs() {
    const jobList = this.state.serverJobs;
    const unfinished = jobList.filter(job => (job.status === "Waiting" || job.status === "Rendering"))
    // For waiting jobs, the stack should reflect the actual queue order on the server from top to bottom.
    // This will naturally put rendering jobs started by autostart at the bottom of this section, however
    // jobs that are started manually will remain in their original queue position.
    unfinished.reverse()
    const stopped = jobList.filter(job => job.status === "Stopped")
    const finished = jobList.filter(job => job.status === "Finished")
    // For stopped and finished jobs, display order is based on the time the job stopped rendering, with
    // the most recent at the top of their respective section. This gives the appearance of jobs moving down
    // the waiting queue, rendering, then stacking up at the bottom.
    stopped.sort((a, b) => a.time_stop < b.time_stop ? 1 : -1)
    finished.sort((a, b) => a.time_stop < b.time_stop ? 1 : -1)

    const sortedJobs = [...unfinished, ...stopped, ...finished]
    this.setState({
      serverJobs: sortedJobs
    })
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

  reloadPage() {
    window.location.reload();
  }

  /**
  * For critical errors. Show a pane with formatted error messages.
  */
  handleError(error) {
    if (error.message === "Network Error") {
      return (
        <div>
          <p className="error-msg">RenderController Web UI unable to connect to server</p>
          <p className="error-txt">There may be a problem with the server or network connectivity.</p>
          <p className="error-txt"><button className="button-left" onClick={this.reloadPage}>Retry</button></p>
        </div>
      )
    } else {
      return (
        <div>
          <p className="error-msg">RenderController Web UI Error</p>
          <p className="error-txt">Error message: {error.message}</p>
        </div>
      )
    }
  }

  render() {
    const { serverJobs, selectedJob, showSettings, error } = this.state;
    if (error) {
      return this.handleError(error);
    }
    return (
      <ul>
        <li className="layout-row">
          <button className="button-left" onClick={this.toggleInputPane}>New</button>
          <button className="button-left" onClick={this.clearFinishedJobs}>Clear Finished</button>
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
