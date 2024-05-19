import pickle
import uuid
from collections.abc import Iterator
from logging import Logger
from minio import Minio
from minio.datatypes import Object as MinioObject
from minio.commonconfig import Tags
from pathlib import Path
from typing import Any
from unidecode import unidecode

from .s3_common import (
    _s3_get_param, _s3_get_params, _s3_except_msg, _s3_log
)


def _access(errors: list[str],
            logger: Logger = None) -> Minio:
    """
    Obtain and return a *MinIO* client object.

    :param errors: incidental error messages
    :param logger: optional logger
    :return: the MinIO client object
    """
    # initialize the return variable
    result: Minio | None = None

    # retrieve the access parameters
    access_key, secret_key, endpoint, secure = _s3_get_params("minio")

    # obtain the MinIO client
    try:
        result = Minio(access_key=access_key,
                       secret_key=secret_key,
                       endpoint=endpoint,
                       secure=secure)
        _s3_log(logger=logger,
                stmt="Minio client created")

    except Exception as e:
        _s3_except_msg(errors=errors,
                       exception=e,
                       engine="minio",
                       logger=logger)
    return result


def _startup(errors: list[str],
             bucket: str,
             logger: Logger = None) -> bool:
    """
    Prepare the *MinIO* client for operations.

    This function should be called just once, at startup,
    to make sure the interaction with the MinIo service is fully functional.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param logger: optional logger
    :return: True if service is fully functional
    """
    # initialize the return variable
    result: bool = False

    # obtain a MinIO client
    client: Minio = _access(errors=errors,
                            logger=logger)

    # was the MinIO client obtained ?
    if client:
        # yes, proceed
        try:
            if not client.bucket_exists(bucket_name=bucket):
                client.make_bucket(bucket_name=bucket)
            result = True
            _s3_log(logger=logger,
                    stmt=f"Started MinIO, bucket={bucket}")
        except Exception as e:
            _s3_except_msg(errors=errors,
                           exception=e,
                           engine="minio",
                           logger=logger)
    return result


def _file_store(errors: list[str],
                bucket: str,
                basepath: Path | str,
                identifier: str,
                filepath: Path | str,
                mimetype: str,
                tags: dict = None,
                client: Minio = None,
                logger: Logger = None) -> bool:
    """
    Store a file at the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to store the file at
    :param identifier: the file identifier, tipically a file name
    :param filepath: the path specifying where the file is
    :param mimetype: the file mimetype
    :param tags: optional metadata describing the file
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: True if the file was successfully stored, False otherwise
    """
    # initialize the return variable
    result: bool = False

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # was the MinIO client obtained ?
    if curr_client:
        # yes, proceed
        remotepath: Path = Path(basepath) / identifier
        # have tags been defined ?
        if tags is None or len(tags) == 0:
            # no
            doc_tags = None
        else:
            # sim, store them
            doc_tags = Tags(for_object=True)
            for key, value in tags.items():
                # normalize text, by removing all diacritics
                doc_tags[key] = unidecode(value)
        # store the file
        try:
            curr_client.fput_object(bucket_name=bucket,
                                    object_name=f"{remotepath}",
                                    file_path=filepath,
                                    content_type=mimetype,
                                    tags=doc_tags)
            result = True
            _s3_log(logger=logger,
                    stmt=(f"Stored {remotepath}, bucket {bucket}, "
                          f"content type {mimetype}, tags {tags}"))
        except Exception as e:
            _s3_except_msg(errors=errors,
                           exception=e,
                           engine="minio",
                           logger=logger)
    return result


def _file_retrieve(errors: list[str],
                   bucket: str,
                   basepath: Path | str,
                   identifier: str,
                   filepath: Path | str,
                   client: Minio = None,
                   logger: Logger = None) -> Any:
    """
    Retrieve a file from the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to retrieve the file from
    :param identifier: the file identifier, tipically a file name
    :param filepath: the path to save the retrieved file at
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: information about the file retrieved
    """
    # initialize the return variable
    result: Any = None

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # was the MinIO client obtained ?
    if curr_client:
        # yes, proceed
        remotepath: Path = Path(basepath) / identifier
        try:
            result = curr_client.fget_object(bucket_name=bucket,
                                             object_name=f"{remotepath}",
                                             file_path=filepath)
            _s3_log(logger=logger,
                    stmt=f"Retrieved {remotepath}, bucket {bucket}")
        except Exception as e:
            if not hasattr(e, "code") or e.code != "NoSuchKey":
                _s3_except_msg(errors=errors,
                               exception=e,
                               engine="minio",
                               logger=logger)
    return result


def _object_exists(errors: list[str],
                   bucket: str,
                   basepath: Path | str,
                   identifier: str | None,
                   client: Minio = None,
                   logger: Logger = None) -> bool:
    """
    Determine if a given object exists in the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to locate the object at
    :param identifier: optional object identifier
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: True if the object was found, false otherwise
    """
    # initialize the return variable
    result: bool = False

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # proceed, if the MinIO client eas obtained
    if curr_client:
        # was the identifier provided ?
        if identifier is None:
            # no, object is a folder
            objs: Iterator = _objects_list(errors=errors,
                                           bucket=bucket,
                                           basepath=basepath,
                                           recursive=False,
                                           client=curr_client,
                                           logger=logger)
            result = next(objs, None) is None
        # verify the status of the object
        elif _object_stat(errors=errors,
                          bucket=bucket,
                          basepath=basepath,
                          identifier=identifier,
                          client=curr_client,
                          logger=logger):
            result = True

        remotepath: Path = Path(basepath) / identifier
        existence: str = "exists" if result else "do not exist"
        _s3_log(logger=logger,
                stmt=f"Object {remotepath}, bucket {bucket}, {existence}")

    return result


def _object_stat(errors: list[str],
                 bucket: str,
                 basepath: Path | str,
                 identifier: str,
                 client: Minio = None,
                 logger: Logger = None) -> MinioObject:
    """
    Retrieve and return the information about an object in the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying where to locate the object
    :param identifier: the object identifier
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: metadata and information about the object
    """
    # initialize the return variable
    result: MinioObject | None = None

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # was the MinIO client obtained ?
    if curr_client:
        # yes, proceed
        remotepath: Path = Path(basepath) / identifier
        try:
            result = curr_client.stat_object(bucket_name=bucket,
                                             object_name=f"{remotepath}")
            _s3_log(logger=logger,
                    stmt=f"Stat'ed {remotepath}, bucket {bucket}")
        except Exception as e:
            if not hasattr(e, "code") or e.code != "NoSuchKey":
                _s3_except_msg(errors=errors,
                               exception=e,
                               engine="minio",
                               logger=logger)
    return result


def _object_store(errors: list[str],
                  bucket: str,
                  basepath: Path | str,
                  identifier: str,
                  obj: Any,
                  tags: dict = None,
                  client: Minio = None,
                  logger: Logger = None) -> bool:
    """
    Store an object at the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to store the object at
    :param identifier: the object identifier
    :param obj: object to be stored
    :param tags: optional metadata describing the object
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: True if the object was successfully stored, False otherwise
    """
    # initialize the return variable
    result: bool = False

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # proceed, if the MinIO client was obtained
    if curr_client:
        # serialize the object into a file
        temp_folder: Path = _s3_get_param("minio", "temp-folder")
        filepath: Path = temp_folder / f"{uuid.uuid4()}.pickle"
        with filepath.open("wb") as f:
            pickle.dump(obj, f)

        # store the file
        op_errors: list[str] = []
        _file_store(errors=op_errors,
                    bucket=bucket,
                    basepath=basepath,
                    identifier=identifier,
                    filepath=filepath,
                    mimetype="application/octet-stream",
                    tags=tags,
                    client=curr_client,
                    logger=logger)

        # errors ?
        if op_errors:
            # yes, report them
            errors.extend(op_errors)
            storage: str = "Unable to store"
        else:
            # no, remove the file from the file system
            result = True
            filepath.unlink()
            storage: str = "Stored "

        remotepath: Path = Path(basepath) / identifier
        _s3_log(logger=logger,
                stmt=f"{storage} {remotepath}, bucket {bucket}")

    return result


def _object_retrieve(errors: list[str],
                     bucket: str,
                     basepath: Path,
                     identifier: str,
                     client: Minio = None,
                     logger: Logger = None) -> Any:
    """
    Retrieve an object from the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to retrieve the object from
    :param identifier: the object identifier
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: the object retrieved
    """
    # initialize the return variable
    result: Any = None

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # proceed, if the MinIO client was obtained
    if curr_client:
        # retrieve the file containg the serialized object
        temp_folder: Path = _s3_get_param("minio", "temp-folder")
        filepath: Path = temp_folder / f"{uuid.uuid4()}.pickle"
        stat: Any = _file_retrieve(errors=errors,
                                   bucket=bucket,
                                   basepath=basepath,
                                   identifier=identifier,
                                   filepath=filepath,
                                   client=curr_client,
                                   logger=logger)

        # was the file retrieved ?
        if stat:
            # yes, umarshall the corresponding object
            with filepath.open("rb") as f:
                result = pickle.load(f)
            filepath.unlink()

        retrieval: str = "Retrieved" if result else "Unable to retrieve"
        remotepath: Path = Path(basepath) / identifier
        _s3_log(logger=logger,
                stmt=f"{retrieval} {remotepath}, bucket {bucket}")

    return result


def _object_delete(errors: list[str],
                   bucket: str,
                   basepath: str,
                   identifier: str = None,
                   client: Minio = None,
                   logger: Logger = None) -> bool:
    """
    Remove an object from the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to retrieve the object from
    :param identifier: optional object identifier
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: True if the object was successfully deleted, False otherwise
    """
    # initialize the return variable
    result: bool = False

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # proceed, if the MinIO client was obtained
    if curr_client:
        # was the identifier provided ?
        if identifier is None:
            # no, remove the folder
            __folder_delete(errors=errors,
                            bucket=bucket,
                            basepath=basepath,
                            client=curr_client,
                            logger=logger)
        else:
            # yes, remove the object
            remotepath: Path = Path(basepath) / identifier
            try:
                curr_client.remove_object(bucket_name=bucket,
                                          object_name=f"{remotepath}")
                result = True
                _s3_log(logger=logger,
                        stmt=f"Deleted {remotepath}, bucket {bucket}")
            except Exception as e:
                if not hasattr(e, "code") or e.code != "NoSuchKey":
                    _s3_except_msg(errors=errors,
                                   exception=e,
                                   engine="minio",
                                   logger=logger)
    return result


def _object_tags_retrieve(errors: list[str],
                          bucket: str,
                          basepath: str,
                          identifier: str,
                          client: Minio = None,
                          logger: Logger = None) -> dict:
    """
    Retrieve and return the metadata information for an object in the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to retrieve the object from
    :param identifier: the object identifier
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: the metadata about the object
    """
    # initialize the return variable
    result: dict | None = None

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # was the MinIO client obtained ?
    if curr_client:
        # yes, proceed
        remotepath: Path = Path(basepath) / identifier
        try:
            tags: Tags = curr_client.get_object_tags(bucket_name=bucket,
                                                     object_name=f"{remotepath}")
            if tags and len(tags) > 0:
                result = {}
                for key, value in tags.items():
                    result[key] = value
            _s3_log(logger=logger,
                    stmt=f"Retrieved {remotepath}, bucket {bucket}, tags {result}")
        except Exception as e:
            if not hasattr(e, "code") or e.code != "NoSuchKey":
                _s3_except_msg(errors=errors,
                               exception=e,
                               engine="minio",
                               logger=logger)

    return result


def _objects_list(errors: list[str],
                  bucket: str,
                  basepath: str,
                  recursive: bool = False,
                  client: Minio = None,
                  logger: Logger = None) -> Iterator:
    """
    Retrieve and return an iterator into the list of objects at *basepath*, in the *MinIO* store.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to iterate from
    :param recursive: whether the location is iterated recursively
    :param client: optional MinIO client (obtains a new one, if not provided)
    :param logger: optional logger
    :return: the iterator into the list of objects, 'None' if the folder does not exist
    """
    # initialize the return variable
    result: Iterator | None = None

    # make sure to have a MinIO client
    curr_client: Minio = client or _access(errors=errors,
                                           logger=logger)
    # was the MinIO client obtained ?
    if curr_client:
        # yes, proceed
        try:
            result = curr_client.list_objects(bucket_name=bucket,
                                              prefix=basepath,
                                              recursive=recursive)
            _s3_log(logger=logger,
                    stmt=f"Listed {basepath}, bucket {bucket}")
        except Exception as e:
            _s3_except_msg(errors=errors,
                           exception=e,
                           engine="minio",
                           logger=logger)

    return result


def __folder_delete(errors: list[str],
                    bucket: str,
                    basepath: str,
                    client: Minio,
                    logger: Logger = None) -> None:
    """
    Traverse the folders recursively, removing its objects.

    :param errors: incidental error messages
    :param bucket: the bucket to use
    :param basepath: the path specifying the location to delete the objects at
    :param client: the MinIO client object
    :param logger: optional logger
    """
    # obtain the list of entries in the given folder
    objs: Iterator = _objects_list(errors=errors,
                                   bucket=bucket,
                                   basepath=basepath,
                                   recursive=True,
                                   logger=logger)
    # was the list obtained ?
    if objs:
        # yes, proceed
        for obj in objs:
            try:
                client.remove_object(bucket_name=bucket,
                                     object_name=obj.object_name)
                _s3_log(logger=logger,
                        stmt=f"Removed folder {basepath}, bucket {bucket}")
            except Exception as e:
                # SANITY CHECK: in case of concurrent exclusion
                if not hasattr(e, "code") or e.code != "NoSuchKey":
                    _s3_except_msg(errors=errors,
                                   exception=e,
                                   engine="minio",
                                   logger=logger)