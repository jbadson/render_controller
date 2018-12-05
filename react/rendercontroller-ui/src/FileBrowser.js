import React, { Component } from 'react';
import axios from 'axios';
import './FileBrowser.css';

/**
 * A file browser widget for navigating the server-side filesystem.
 * @param {string} path - Initial directory to list on server.
 * @param {string} url - URL of API
 * @param {function} onFileClick - Action to take when a file is clicked.
 */
class FileBrowser extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: null,
      fileList: [],
      pathHistory: [],
      error: null,
    };
    this.onFileClick = props.onFileClick.bind(this);
    this.handleDirClick = this.handleDirClick.bind(this);
    this.handleBackClick = this.handleBackClick.bind(this);
  }

  getDirContents(path) {
    return axios.post(this.props.url, {"path": path});
  }

  componentDidMount() {
    this.handleDirClick(this.props.path);
  }

  handleDirClick(path) {
    this.getDirContents(path)
      .then(
        (result) => {
          this.setState(state => {
            const history = state.pathHistory;
            return ({
              fileList: result.data.contents,
              pathHistory: history.concat([state.path]),
              path: result.data.current,
            })
          });
        },
        (error) => {
          this.setState({error: error});
        },
      );
  }

  handleBackClick() {
    const history = this.state.pathHistory;
    const path = history[history.length - 1]
    if (!path) {
      return;
    }
    this.getDirContents(path).then(
      (result) => {
        this.setState({
          fileList: result.data.contents,
          pathHistory: history.slice(0, history.length -1),
          path: path,
        });
      },
      (error) => {
        this.setState({error: error});
      },
    );
  }

  renderLine(line) {
    // Do not show hidden files
    if (line.name.startsWith(".")) {
      return;
    }
    // Format based on file type
    let className = "browser";
    let handler;
    if (line.type === "d") {
      className += "-dir";
      handler = this.handleDirClick;
    } else {
      // Treat symlinks as files because we can't tell what they point to.
      className += "-file";
      handler = this.onFileClick;
    }
    return(
      <li
          className={className}
          onClick={() => handler(line.path)}
          key={line.path}
      >
        {line.name}
      </li>
    );
  }

  renderBackButton() {
    if (!this.state.pathHistory[this.state.pathHistory.length - 1]) {
      return  null;
    }
    return (
      <li className="browser" onClick={this.handleBackClick}>
        &#8656; Back
      </li>
    )
  }

  render() {
    const { fileList, error } = this.state;
    if (error) {
      return <p>FileBrowser load failed: {error.message}</p>
    }
    return (
        <ul>
          {this.renderBackButton()}
          <li className="browser-current">[{this.state.path}]</li>
          {fileList.map(line => this.renderLine(line))}
        </ul>
    );
  }
}


export default FileBrowser;
