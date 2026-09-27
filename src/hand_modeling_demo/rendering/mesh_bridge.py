from math import cos, pi, sqrt

from panda3d.core import (
    CollisionNode,
    CollisionPolygon,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Point3,
)


def mesh_to_geom_node(mesh, name: str) -> GeomNode:
    data = GeomVertexData(name, GeomVertexFormat.getV3n3(), Geom.UHStatic)
    data.setNumRows(len(mesh.faces) * 3)
    vertices = GeomVertexWriter(data, "vertex")
    normals = GeomVertexWriter(data, "normal")

    adjacent_faces: list[list[int]] = [[] for _ in mesh.vertices]
    for face_index, face in enumerate(mesh.faces):
        for vertex_index in face:
            adjacent_faces[int(vertex_index)].append(face_index)

    crease_cosine = cos(45.0 * pi / 180.0)
    triangles = GeomTriangles(Geom.UHStatic)
    row = 0
    for face_index, face in enumerate(mesh.faces):
        reference = mesh.face_normals[face_index]
        for vertex_index in face:
            vertex = mesh.vertices[int(vertex_index)]
            smooth = [0.0, 0.0, 0.0]
            for adjacent_index in adjacent_faces[int(vertex_index)]:
                candidate = mesh.face_normals[adjacent_index]
                dot = sum(float(reference[axis] * candidate[axis]) for axis in range(3))
                if dot >= crease_cosine:
                    for axis in range(3):
                        smooth[axis] += float(candidate[axis])
            length = sqrt(sum(value * value for value in smooth)) or 1.0
            vertices.addData3f(*(float(value) for value in vertex))
            normals.addData3f(*(value / length for value in smooth))
        triangles.addVertices(row, row + 1, row + 2)
        triangles.closePrimitive()
        row += 3
    geometry = Geom(data)
    geometry.addPrimitive(triangles)
    node = GeomNode(name)
    node.addGeom(geometry)
    return node


def mesh_to_collision_node(mesh, name: str) -> CollisionNode:
    node = CollisionNode(name)
    for face in mesh.faces:
        points = [
            Point3(*(float(value) for value in mesh.vertices[int(index)]))
            for index in face
        ]
        node.addSolid(CollisionPolygon(*points))
    return node
