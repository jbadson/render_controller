import React, { Component } from 'react';
import './FileBrowser.css';
import axios from 'axios';
import { fmtUnixTimestamp } from './util';

// TODO: Doesn't remember sort mode when using the back arrow in file browser

/**
 * A file browser widget for navigating the server-side filesystem.
 * @prop {string} path - Initial directory to list on server.
 * @prop {function} onFileClick - Action to take when a file is clicked.
 */
class FileBrowser extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: null,
      fileList: [],
      pathHistory: [],
      sortBy: "name",
      error: null,
    };
    this.onFileClick = props.onFileClick.bind(this);
    this.handleDirClick = this.handleDirClick.bind(this);
    this.handleBackClick = this.handleBackClick.bind(this);
    this.sortFiles = this.sortFiles.bind(this);
  }

  getDirContents(path) {
    return axios.post(process.env.REACT_APP_BACKEND_API + "/storage/ls", {"path": path});
  }

  componentDidMount() {
    this.handleDirClick(this.props.path);
  }

  sortByKind(fileList) {
    // Puts directories first, then sorts by file extension
    const dirs = fileList.filter(file => file.type === "d");
    const files = fileList.filter(file => file.type !== "d").sort(
      function(a, b) {return a.ext > b.ext}
    );
    return [...dirs, ...files];
  }

  sortFiles(sortBy = null) {
    const newSort = sortBy || this.state.sortBy;
    const prevSort = this.state.sortBy;
    const fileList = this.state.fileList;

    if (sortBy === prevSort) {
      fileList.reverse();
      this.setState({fileList: fileList});
      return;
    }

    var sortedList;
    if (newSort === "name") {
      sortedList = fileList.sort(function(a, b) {return a.name > b.name})
    } else if (newSort === "size") {
      sortedList = fileList.sort(function(a, b) {return a.size - b.size})
    } else if (newSort === "mtime") {
      sortedList = fileList.sort(function(a, b) {return a.mtime - b.mtime})
    } else if (newSort === "ctime") {
      sortedList = fileList.sort(function(a, b) {return a.ctime - b.ctime})
    } else if (newSort === "kind") {
      sortedList = this.sortByKind(fileList);
    }

    this.setState({
        sortBy: sortBy,
        fileList: sortedList
    })
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
      )
      .then(() => {this.sortFiles()});
  }

  handleBackClick() {
    const history = this.state.pathHistory;
    const sortBy = this.state.sortBy;
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
    )
    .then(() => {this.sortFiles(sortBy)});
  }

  renderLine(line) {
    // Do not show hidden files
    if (line.name.startsWith(".")) {
      return;
    }
    // Convert mtime
    const mtime = fmtUnixTimestamp(line.mtime);
    const ctime = fmtUnixTimestamp(line.ctime);
    // Format based on file type
    let icon = "file_sm.png";
    let handler;
    let kind;
    if (line.type === "d") {
      icon = "folder_sm.png";
      handler = this.handleDirClick;
      kind = "directory";
    } else {
      // Treat symlinks as files because we can't tell what they point to.
      handler = this.onFileClick;
      kind = line.ext || "other";
    }
    return(
      <tr
          onClick={() => handler(line.path)}
          key={line.path}
      >
        <td className="fb-left">
          <img src={icon} alt="" className="fb-icon" />{line.name}
        </td>
        <td className="fb-right">{mtime.toString()}</td>
        <td className="fb-right">{ctime.toString()}</td>
        <td className="fb-right">{kind}</td>
      </tr>
    );
  }

  renderBackButton() {
    let className = "fb-back-button";
    if (!this.state.pathHistory[this.state.pathHistory.length - 1]) {
      className += "-disabled";
    }
    return (
      <span className={className} onClick={this.handleBackClick}>
        &#8617;
      </span>
    )
  }

  render() {
    const { fileList, error } = this.state;
    if (error) {
      return <p>FileBrowser load failed: {error.message}</p>
    }
    return (
      <ul>
        <li className="fb-row">
          <div className="fb-pathbar">
            {this.renderBackButton()} {this.state.path}
          </div>
        </li>
        <li className="fb-row">
          <div className="fb-labels">
            <span className="fb-left" onClick={() => this.sortFiles("name")}>Name</span>
            <span className="fb-right" onClick={() => this.sortFiles("kind")}>Kind</span>
            <span className="fb-right" onClick={() => this.sortFiles("ctime")}>Date Created</span>
            <span className="fb-right" onClick={() => this.sortFiles("mtime")}>Date Modified</span>
          </div>
        </li>
        <li className="fb-row">
          <div className="fb-inner" >
          <table className="fb-table">
            <tbody>
              {fileList.map(line => this.renderLine(line))}
            </tbody>
          </table>
          </div>
        </li>
      </ul>
    );
  }
}


/**
 * Displays FileBrowser in a popup overlay.
 * @prop {string} path - Initial directory to list on server.
 * @prop {function} onFileClick - Action to take when a file is clicked.
 * @prop {function} onClose - Action to take when window is closed.
 */
class FileBrowserPopup extends Component {
  constructor(props) {
    super(props);
    this.node = React.createRef();
    this.handleClick = this.handleClick.bind(this);
  }

  componentWillMount() {
    document.addEventListener('mousedown', this.handleClick, false);
  }

  componentWillUnmount() {
    document.removeEventListener('mousedown', this.handleClick, false);
  }

  handleClick(event) {
    if (this.node.current.contains(event.target)){
      // Ingore clicks inside this component
      return;
    }
    this.props.onClose();
  }

  render() {
  return (
      <div className="fb-container" ref={this.node}>
        <ul>
          <li className="fb-row">
            <div className="fb-header">
              Select project file on file server
              <div className="fb-closebutton" onClick={this.props.onClose}>X</div>
            </div>
          </li>
          <li className="layout-row">
            <FileBrowser
              path={this.props.path}
              onFileClick={this.props.onFileClick}
            />
          </li>
        </ul>
      </div>
    )
  }
}


export { FileBrowser, FileBrowserPopup };
